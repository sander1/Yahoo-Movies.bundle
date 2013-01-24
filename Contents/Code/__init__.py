YM_MOVIE_URL = 'http://movies.yahoo.com/movie/%s/production-details.html'
YM_SEARCH_URL = 'http://movies.search.yahoo.com/search?p=%s&section=listing'
JB_POSTER_YEAR = 'http://www.joblo.com/upcomingmovies/%d/%s'

REQUEST_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:18.0) Gecko/20100101 Firefox/18.0',
	'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
	'Accept-Language': 'en-US,en;q=0.5',
	'Accept-Encoding': 'gzip, deflate',
	'DNT': '1',
	'Connection': 'keep-alive'
}

RE_TITLE_URL = Regex('[^a-z0-9 ]')
RE_DURATION = Regex('(?P<hours>\d+) hours?( (?P<minutes>\d+) minutes?)?')

####################################################################################################
def Start():

	HTTP.CacheTime = CACHE_1MONTH

####################################################################################################
class YahooMoviesAgent(Agent.Movies):

	name = 'Yahoo Movies'
	languages = [Locale.Language.English]
	primary_provider = True

	def search(self, results, media, lang):
		if media.year and int(media.year) > 1900:
			try:
				html = HTML.ElementFromURL(self.movie_url(media.name), headers=REQUEST_HEADERS, sleep=2.0)
				title = html.xpath('//h1[@property="name"]/text()')[0]
				year = int(html.xpath('//h1[@property="name"]/span[@class="year"]/text()')[0].strip('()'))
				score = 100

				# Accept a 1 year difference in release year as a good match. Yahoo Movies shows US
				# release dates -- international movies sometimes have a US release 1 year later than
				# the international release.
				if abs(int(media.year) - year) <= 1:
					Log("Adding: %s (%d); score: %d" % (title, year, score))
					results.Append(MetadataSearchResult(
						id = self.movie_guid(media.name),
						name = title,
						year = year,
						score = score,
						lang = 'en'
					))
			except:
				pass

		if len(results) == 0:
			url = self.search_url(media.name)
			try:
				if media.year and int(media.year) < Datetime.Now().year:
					cache_time = CACHE_1MONTH
				else:
					cache_time = CACHE_1DAY

				html = HTML.ElementFromURL(url, headers=REQUEST_HEADERS, cacheTime=cache_time, sleep=2.0)
			except:
				Log("Error fetching search data from Yahoo Movies: %s" % url)

			if html:
				for movie in html.xpath('//h3[@class="title"]/a[contains(@href, "movies.yahoo.com/movie/")]'):
					id = movie.get('href').strip('/').split('/')[-1]
					title = ''.join(movie.xpath('.//text()'))
					year = None
					score = 100

					if title[-6:-5] == '(' and title[-1:] == ')':
						(title, year) = title.rstrip(')').rsplit(' (', 1)
						year = int(year)

					score = score - abs(String.LevenshteinDistance(id, self.movie_guid(media.name)))

					if media.year and year:
						score = score - abs(int(media.year) - year)

					Log("Adding: %s (%d); score: %d" % (title, year, score))
					results.Append(MetadataSearchResult(
						id = id,
						name = title,
						year = year,
						score = score,
						lang = 'en'
					))

		if len(results) == 0:
			Log("Couldn't find a match for: %s" % String.Unquote(media.filename))


	def update(self, metadata, media, lang):

		url = YM_MOVIE_URL % metadata.id
		try:
			html = HTML.ElementFromURL(url, headers=REQUEST_HEADERS, sleep=2.0)
		except:
			Log("Error fetching data from Yahoo Movies: %s" % url)

		if html:
			# Title, year and summary
			metadata.title = html.xpath('//h1[@property="name"]/text()')[0]
			metadata.year = int(html.xpath('//h1[@property="name"]/span[@class="year"]/text()')[0].strip('()'))
			metadata.summary = html.xpath('//h3[text()="Synopsis"]/parent::div/following-sibling::div/text()')[0]

			# Content rating
			try:
				content_rating_str = html.xpath('//h4[text()="MPAA Rating"]/parent::td/following-sibling::td/text()')[0].strip().replace(' ', '-')
				if content_rating_str in ('G', 'PG', 'PG-13', 'R', 'NC-17'):
					metadata.content_rating = content_rating_str
			except:
				metadata.content_rating = None

			# Duration
			try:
				duration = 0
				duration_str = html.xpath('//h4[text()="Run Time"]/parent::td/following-sibling::td/text()')[0]
				d = RE_DURATION.search(duration_str).groupdict()

				if 'hours' in d:
					duration += int(d['hours']) * 60 * 60 * 1000
				if 'minutes' in d:
					duration += int(d['minutes']) * 60 * 1000

				if duration > 0:
					metadata.duration = duration
			except:
				metadata.duration = None

			# Genres
			metadata.genres.clear()
			try:
				genres_str = html.xpath('//h4[text()="Genres"]/parent::td/following-sibling::td/text()')[0].replace('/', ', ') # Split Action/Adventure, Sci-Fi/Fantasy
				genres = genres_str.split(', ')

				for genre in genres:
					if genre in ('Action', 'Adventure', 'Animated', 'Comedy', 'Crime', 'Drama', 'Family', 'Fantasy', 'Foreign', 'Horror', 'Musical', 'Romance', 'Sci-Fi', 'Thriller', 'War'):
						metadata.genres.add(genre)
			except:
				pass

			# Originally available
			try:
				originally_available_at_str = html.xpath('//h4[text()="In Theaters"]/parent::td/following-sibling::td//text()')[0]
				metadata.originally_available_at = Datetime.ParseDate(originally_available_at_str).date()
			except:
				metadata.originally_available_at = None

			# Studio
			try:
				studio_str = html.xpath('//h4[text()="Distributors"]/parent::td/following-sibling::td/text()')[0].split(',')[0].replace(' Releasing', '')
				metadata.studio = studio_str
			except:
				metadata.studio = None

			# Directors
			metadata.directors.clear()
			try:
				director = html.xpath('//td[text()="Director"]/preceding-sibling::td//text()')[0]
				metadata.directors.add(director)
			except:
				pass

			# Posters
			try:
				current_posters = [] # Keep track of available posters
				index = 0
				poster_html = HTML.ElementFromURL(JB_POSTER_YEAR % (metadata.year, metadata.id), headers=REQUEST_HEADERS, sleep=2.0)

				for url in reversed(poster_html.xpath('//img[contains(@alt, "Movie Posters")]/@src')):
					index = index + 1

					if not url.startswith('http://'):
						url = 'http://www.joblo.com%s' % url

					preview_url = url.replace('/thumb/', '/large/')
					poster_url = url.replace('/thumb/', '/full/')
					current_posters.append(poster_url)

					if poster_url not in metadata.posters:
						preview = HTTP.Request(preview_url, headers=REQUEST_HEADERS, sleep=2.0).content
						metadata.posters[poster_url] = Proxy.Preview(preview, sort_order=index)

				# Remove unavailable posters
				for key in metadata.posters.keys():
					if key not in current_posters:
						del metadata.posters[key]
			except:
				pass


	def movie_guid(self, title):

		title = String.StripDiacritics(title).lower()
		title = RE_TITLE_URL.sub('', title).strip()
		title = title.replace(' ', '-')
		return title


	def movie_url(self, title):

		title = self.movie_guid(title)
		url = YM_MOVIE_URL % title
		return url


	def search_url(self, title):

		title = String.Quote(title, usePlus=True)
		url = YM_SEARCH_URL % title
		return url
