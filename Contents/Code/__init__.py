import struct

YM_MOVIE_URL = 'http://movies.yahoo.com/movie/%s/'
YM_SEARCH_URL = 'http://movies.search.yahoo.com/search?p=%s&section=listing'
JB_POSTER_YEAR = 'http://www.joblo.com/upcomingmovies/movieindex.php?year=%d&show_all=true'
IA_POSTER_YEAR = 'http://www.impawards.com/%d/std.html'

REQUEST_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.117 Safari/537.36',
	'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
	'Accept-Language': 'en-US,en;q=0.8',
	'Accept-Encoding': 'gzip,deflate,sdch',
	'DNT': '1',
	'Connection': 'keep-alive'
}

RE_TITLE_URL = Regex('[^a-z0-9 ]')
RE_DURATION = Regex('(?P<hours>\d+) hours?( (?P<minutes>\d+) minutes?)?')
RE_JB_FILTER = Regex('\-(banner|brazil|dutch|french|int|japan(ese)?|quad|russian)\-', Regex.IGNORECASE)

CACHE_TIME = 8640000 # 100 days
DEBUG = False

####################################################################################################
def Start():

	HTTP.CacheTime = CACHE_TIME

	if DEBUG:
		Dict.Reset()

	now = int(Datetime.TimestampFromDatetime(Datetime.Now()))
	if 'created' in Dict:
		if now - Dict['created'] > CACHE_TIME:
			Dict.Reset()

	if 'created' not in Dict:
		Dict['created'] = now
		for source in ('ym', 'jb', 'ia'):
			Dict[source] = {}

		Dict['ym']['skip_media_guid'] = []
		Dict.Save()

####################################################################################################
class YahooMoviesAgent(Agent.Movies):

	name = 'Yahoo Movies'
	languages = [Locale.Language.English]
	primary_provider = True
	accepts_from = ['com.plexapp.agents.localmedia']
	contributes_to = ['com.plexapp.agents.imdb']
	fallback_agent = 'com.plexapp.agents.imdb'

	def search(self, results, media, lang):

		if media.primary_metadata:
			media_name = media.primary_metadata.title
			media_year = media.primary_metadata.year
		else:
			media_name = media.name
			media_year = media.year

		media_guid = self.movie_guid(media_name)

		if media_year and int(media_year) > 1900 and media_guid not in Dict['ym']['skip_media_guid']:
			try:
				html = HTML.ElementFromURL(YM_MOVIE_URL % media_guid, headers=REQUEST_HEADERS, sleep=2.0)
			except:
				html = None

				if int(media_year) < Datetime.Now().year - 1:
					Dict['ym']['skip_media_guid'].append(media_guid)
					Dict.Save()
					Log(" --> YM: Adding '%s' to skip_media_guid list" % media_guid)
					if DEBUG: Log(Dict['ym']['skip_media_guid'])

			if html:
				score = 100
				title = html.xpath('//meta[@property="og:title"]/@content')[0]

				try:
					year = int(html.xpath('//span[@class="year"]/text()')[0].strip('()'))
				except:
					year = int(media_year)

				# Accept a 1 year difference in release year as a good match. Yahoo Movies shows US
				# release dates -- international movies sometimes have a US release 1 year later than
				# the international release.
				if abs(int(media_year) - year) <= 1:
					Log(" --> YM: Adding: %s (%d); score: %d (perfect match)" % (title, year, score))
					results.Append(MetadataSearchResult(
						id = media_guid,
						name = title,
						year = year,
						score = score,
						lang = 'en'
					))

		if len(results) == 0:
			try:
				if media_year and int(media_year) < Datetime.Now().year - 1:
					cache_time = CACHE_TIME
				else:
					cache_time = CACHE_1DAY

				html = HTML.ElementFromURL(self.search_url(media_name), headers=REQUEST_HEADERS, cacheTime=cache_time, sleep=2.0)
			except:
				html = None
				Log(" --> YM: Error fetching search data from Yahoo Movies: %s" % url)

			if html:
				for movie in html.xpath('//h3[@class="title"]/a[contains(@href, "movies.yahoo.com/movie/")]'):
					id = movie.get('href').strip('/').split('/')[-1]
					title = movie.text_content()
					year = 0
					score = 90
					score_explanation = ''

					if title[-6:-5] == '(' and title[-1:] == ')':
						(title, year) = title.rstrip(')').rsplit(' (', 1)
						year = int(year)

					# Strip the year off the id (if it's there) when comparing with our own created id
					if media_year and id.endswith('-%s' % media_year):
						id_compare = id.rsplit('-',1)[0]
					else:
						id_compare = id

					# Use difference between the 2 strings to subtract points from the score
					title_diff = abs(String.LevenshteinDistance(id_compare, media_guid))
					if DEBUG: score_explanation += '\n  Found id: %s\n    Our id: %s\ntitle_diff: %d\n     score: %d - %d = %d\n' % (id_compare, media_guid, title_diff, score, title_diff, score-title_diff)
					score = score - title_diff

					# Compare years. Give bonus if year difference is 0 or 1. Otherwise subtract points based on the difference in years
					if media_year and int(media_year) > 1900 and year > 1900:
						year_diff = abs(int(media_year) - year)
						if DEBUG: score_explanation += '\nFound year: %d\n  Our year: %s\n year_diff: %d\n     score: %d ' % (year, media_year, year_diff, score)

						if year_diff <= 1:
							score = score + 10
							if DEBUG: score_explanation += '+ 10 (bonus) = %d\n' % score
						else:
							score = score - (5 * year_diff)
							if DEBUG: score_explanation += '- (5 * %d) = %d\n' % (year_diff, score)

					if score <= 0:
						Log(" --> YM: Not adding: %s (%d); score: %d%s" % (title, year, score, score_explanation))
					else:
						Log(" --> YM: Adding: %s (%d); score: %d%s" % (title, year, score, score_explanation))
						results.Append(MetadataSearchResult(
							id = id,
							name = title,
							year = year,
							score = score,
							lang = 'en'
						))

		if len(results) == 0:
			Log(" --> YM: Couldn't find a match for: %s" % media_name)


	def update(self, metadata, media, lang):

		url = YM_MOVIE_URL % metadata.id
		try:
			html = HTML.ElementFromURL(url, headers=REQUEST_HEADERS, sleep=2.0)
		except:
			html = None
			Log(" --> YM: Error fetching data from Yahoo Movies: %s" % url)

		if html:
			# Title, year and summary
			metadata.title = html.xpath('//h1[@property="name"]/text()')[0]

			try:
				year = int(html.xpath('//h4[text()="In Theaters"]/parent::td/following-sibling::td//text()')[0].split(', ')[-1])
			except:
				try:
					year = int(html.xpath('//h1[@property="name"]/span[@class="year"]/text()')[0].strip('()'))
				except:
					year = None

			if year and year > 1900 and year <= Datetime.Now().year:
				metadata.year = year

			summary = html.xpath('//h3[text()="Synopsis"]/parent::div/following-sibling::div/text()')
			metadata.summary = '\n\n'.join([paragraph.strip() for paragraph in summary])

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
				studio_str = html.xpath('//h4[text()="Distributors"]/parent::td/following-sibling::td/text()')[0].split(',')[0].replace(' Releasing', '').replace(' Distribution', '')
				metadata.studio = studio_str
			except:
				metadata.studio = None

			# Country
			metadata.countries.clear()
			try:
				country = html.xpath('//h4[text()="Produced In"]/parent::td/following-sibling::td/text()')[0].split(',')[0].strip()
				metadata.countries.add(country)
			except:
				pass

			# Rating
			try:
				rating_str = html.xpath('//strong[@class="avg-value"]/text()')[0]
				metadata.rating = float(rating_str) * 2
			except:
				metadata.rating = None

			# Directors
			metadata.directors.clear()
			try:
				director = html.xpath('//td[text()="Director"]/preceding-sibling::td//text()')[0]
				metadata.directors.add(director)
			except:
				pass

			# Cast
			metadata.roles.clear()
			for movie_role in html.xpath('//h3[text()="CAST"]/parent::div/following-sibling::div/table//tr'):
				role = metadata.roles.new()
				role.actor = movie_role.xpath('./td')[0].text_content()
				role.role = movie_role.xpath('./td/text()')[0]

			# Posters
			current_posters = [] # Keep track of available posters
			index = 0

			if DEBUG:
				for key in metadata.posters.keys():
					del metadata.posters[key]

			if Prefs['get_posters']:
				preview_url = html.xpath('//img[starts-with(@alt, "Poster of ") and contains(@src, "yimg.com")]/@src')
				if len(preview_url) == 1:
					poster_url = 'http://%s' % preview_url[0].rsplit('http://',1)[1]

					if poster_url not in metadata.posters:
						preview_img = self.poster_check('ym', metadata.id, preview_url[0], poster_url)

						if preview_img:
							index = index + 1
							metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)
							current_posters.append(poster_url)
					else:
						current_posters.append(poster_url)

				if metadata.year and metadata.year >= 1980:
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

							if poster_url not in metadata.posters:
								preview_img = self.poster_check('jb', metadata.id, preview_url)

								if preview_img:
									index = index + 1
									metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)
									current_posters.append(poster_url)
							else:
								current_posters.append(poster_url)

				if len(current_posters) < 3:
					if metadata.year:
						year = metadata.year
					else:
						year = Datetime.Now().year

					poster_html = HTML.ElementFromURL(IA_POSTER_YEAR % year, headers=REQUEST_HEADERS, sleep=2.0)
					id = self.movie_guid(metadata.title, True)
					posters = poster_html.xpath('//td/font/text()[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ:\'- ", "abcdefghijklmnopqrstuvwxyz"), "%s")]/parent::font/parent::td/following-sibling::td//img/@src' % id)
					ia_poster_succes = False

					for url in posters:
						preview_url = 'http://www.impawards.com/%d/%s' % (year, url)
						poster_url = 'http://www.impawards.com/%d/posters/%s_xlg.jpg' % (year, url.split('/imp_')[-1].strip('.jpg'))

						if poster_url not in metadata.posters:
							preview_img = self.poster_check('ia', metadata.id, preview_url, poster_url)

							if preview_img:
								index = index + 1
								metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)
								current_posters.append(poster_url)
								ia_poster_succes = True
						else:
							current_posters.append(poster_url)
							ia_poster_succes = True

					if not ia_poster_succes and len(posters) > 0:
						preview_url = 'http://www.impawards.com/%d/%s' % (year, posters[0])
						poster_url = 'http://www.impawards.com/%d/posters/%s.jpg' % (year, posters[0].split('/imp_')[-1].strip('.jpg'))

						if poster_url not in metadata.posters:
							preview_img = self.poster_check('ia', metadata.id, preview_url, poster_url, min_filesize=0)

							if preview_img:
								index = index + 1
								metadata.posters[poster_url] = Proxy.Preview(preview_img, sort_order=index)
								current_posters.append(poster_url)
						else:
							current_posters.append(poster_url)

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


	def search_url(self, title):

		title = String.Quote(title, usePlus=True)
		url = YM_SEARCH_URL % title
		return url


	def poster_check(self, source, metadata_id, preview_url, poster_url=None, min_filesize=102400):

		if not preview_url.endswith('.jpg') or (self.poster_blacklisted(source, metadata_id, preview_url) and min_filesize > 0):
			return None

		if source == 'jb':
			img = preview_url.rsplit('/',1)[-1].strip('.jpg')

			jb_filter = RE_JB_FILTER.search(img)
			if jb_filter:
				self.blacklist_poster(source, metadata_id, preview_url, 'Match found in JB_POSTER_FILTER: %s' % jb_filter.group(0))
				return None

		preview_img = HTTP.Request(preview_url, headers=REQUEST_HEADERS, sleep=2.0).content

		try:
			i = preview_img.find('\xff\xc0') + 5;
			y, x = struct.unpack('>HH', preview_img[i:i+4])

			if x > y:
				self.blacklist_poster(source, metadata_id, preview_url, 'Horizontally oriented poster')
				return None
			if float(x)/float(y) < 0.66:
				self.blacklist_poster(source, metadata_id, preview_url, 'Poster has strange aspect ratio')
				return None
		except:
			pass

		if poster_url:
			if not poster_url.endswith('.jpg'):
				self.blacklist_poster(source, metadata_id, preview_url, 'Poster is not a JPEG')
				return None

			try:
				headers = HTTP.Request(poster_url, headers=REQUEST_HEADERS, sleep=2.0).headers
			except:
				self.blacklist_poster(source, metadata_id, preview_url, 'HTTP error')

			if 'content-type' not in headers or headers['content-type'] != 'image/jpeg':
				self.blacklist_poster(source, metadata_id, preview_url, 'Content-Type header missing or not \'image/jpeg\'')
				return None

			if 'content-length' not in headers or int(headers['content-length']) < min_filesize:
				self.blacklist_poster(source, metadata_id, preview_url, 'Content-Length header missing or filesize less than %dkb' % (min_filesize/1024))
				return None

		return preview_img


	def poster_blacklisted(self, source, metadata_id, url):

		img = url.rsplit('/',1)[-1].strip('.jpg')

		if metadata_id in Dict[source] and img in Dict[source][metadata_id]:
			Log(" --> YM: Image '%s' (source: %s) found on blacklist for '%s'. Skipping..." % (img, source, metadata_id))
			return True

		return False


	def blacklist_poster(self, source, metadata_id, url, reason='Not given'):

		img = url.rsplit('/',1)[-1].strip('.jpg')

		if metadata_id not in Dict[source]:
			Dict[source][metadata_id] = []

		if img not in Dict[source][metadata_id]:
			Dict[source][metadata_id].append(img)
			Log(" --> YM: Image '%s' (source: %s) blacklisted for '%s'. Reason: %s" % (img, source, metadata_id, reason))

		Dict.Save()
		return
