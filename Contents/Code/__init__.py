import struct

YM_MOVIE_URL = 'http://movies.yahoo.com/movie/%s/production-details.html'
YM_SEARCH_URL = 'http://movies.search.yahoo.com/search?p=%s&section=listing'
JB_POSTER_YEAR = 'http://www.joblo.com/upcomingmovies/movieindex.php?year=%d&show_all=true'

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
					year = 0
					score = 100

					if title[-6:-5] == '(' and title[-1:] == ')':
						(title, year) = title.rstrip(')').rsplit(' (', 1)
						year = int(year)

					# Strip the year off the id (if it's there) when comparing with our own created id
					if media.year and id.endswith('-%s' % media.year):
						id_compare = id.rsplit('-',1)[0]
					else:
						id_compare = id

					# Use difference between the 2 strings to subtract points from the score
					score = score - abs(String.LevenshteinDistance(id_compare, self.movie_guid(media.name)))

					# Compare years. Give bonus if year difference is 0 or 1. Otherwise subtract points based on the difference in years
					if media.year and int(media.year) > 1900 and year > 1900:
						year_diff = abs(int(media.year) - year)

						if year_diff <= 1:
							score = score + 10
						else:
							score = score - (5 * year_diff)

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
			current_posters = [] # Keep track of available posters
			index = 0

			preview_url = html.xpath('//img[starts-with(@alt, "Poster of ") and contains(@src, "yimg.com")]/@src')
			if len(preview_url) == 1:
				poster_url = 'http://%s' % preview_url[0].rsplit('http://',1)[1]

				headers = HTTP.Request(poster_url, headers=REQUEST_HEADERS, sleep=2.0).headers
				if 'content-length' in headers and int(headers['content-length']) > 102400:
					current_posters.append(poster_url)

					if poster_url not in metadata.posters:
						index = index + 1
						preview_img = self.poster_check(preview_url)

						if preview_img:
							metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)

			if metadata.year >= 1980:
				html = HTML.ElementFromURL(JB_POSTER_YEAR % metadata.year, headers=REQUEST_HEADERS, sleep=2.0)
				details_url = html.xpath('//a[contains(@href, "%s")]/img/parent::a/@href' % metadata.id)

				if len(details_url) < 1:
					id = self.movie_guid(metadata.title, True)
					details_url = html.xpath('//a[contains(translate(@href, "-", ""), "%s")]/img/parent::a/@href' % id)

				if len(details_url) < 1 and ': ' in metadata.title:
					id = self.movie_guid(metadata.title.split(': ')[0], True)
					details_url = html.xpath('//a[contains(translate(@href, "-", ""), "%s")]/img/parent::a/@href' % id)

				if len(details_url) > 0:
					details_url = details_url[0]
					if not details_url.startswith('http://'):
						details_url = 'http://www.joblo.com%s' % details_url

					poster_html = HTML.ElementFromURL(details_url, headers=REQUEST_HEADERS, sleep=2.0)

					for url in reversed(poster_html.xpath('//img[contains(@alt, "Movie Posters")]/@src')):
						if not url.startswith('http://'):
							url = 'http://www.joblo.com%s' % url

						preview_url = url.replace('/thumb/', '/large/')
						poster_url = url.replace('/thumb/', '/full/')
						current_posters.append(poster_url)

						if poster_url not in metadata.posters:
							preview_img = self.poster_check(preview_url)

							if preview_img:
								index = index + 1
								metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)

				# Remove unavailable posters
				for key in metadata.posters.keys():
					if key not in current_posters:
						del metadata.posters[key]


	def movie_guid(self, title, strip_dashes=False):

		title = String.StripDiacritics(title).lower()
		title = RE_TITLE_URL.sub('', title).strip()
		title = title.replace(' ', '-')

		if strip_dashes:
			title = title.replace('-', '')

		return title


	def movie_url(self, title):

		title = self.movie_guid(title)
		url = YM_MOVIE_URL % title
		return url


	def search_url(self, title):

		title = String.Quote(title, usePlus=True)
		url = YM_SEARCH_URL % title
		return url


	def poster_check(self, preview_url):

		preview_img = HTTP.Request(preview_url, headers=REQUEST_HEADERS, sleep=2.0).content

		try:
			i = preview_img.find('\xff\xc0') + 5;
			y, x = struct.unpack('>HH', preview_img[i:i+4])

			if x > y:
				return None
			elif float(x)/float(y) < 0.66:
				return None
			else:
				return preview_img
		except:
			return None
