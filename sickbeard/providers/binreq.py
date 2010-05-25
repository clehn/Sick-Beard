# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.



import urllib
import urllib2
import os.path
import sys
import datetime
import re

import xml.etree.cElementTree as etree

import sickbeard

from sickbeard import helpers, classes

from sickbeard import exceptions
from sickbeard.common import *
from sickbeard import logger
from sickbeard import tvcache

providerType = "nzb"
providerName = "BinReq"

def isActive():
	return sickbeard.BINREQ and sickbeard.USE_NZB

def getBinReqURL (url):

	result = None

	try:
		f = urllib2.urlopen(url)
		result = "".join(f.readlines())
	except (urllib.ContentTooShortError, IOError), e:
		logger.log("Error loading Bin-Req URL: " + str(sys.exc_info()) + " - " + str(e), logger.ERROR)
		return None

	return result

						
def downloadNZB (nzb):

	logger.log("Downloading an NZB from Bin-Req at " + nzb.url)

	fileName = os.path.join(sickbeard.NZB_DIR, nzb.extraInfo[0] + ".nzb.gz")

	nzbDownloadURL = "http://www.bin-req.net/download.php?nzbid="
	
	# get the request page
	f = urllib.urlopen(nzb.url)
	requestPage = f.readlines();
	f.close()
	
	# find the nzb id
	nzbID = None
	for curLine in requestPage:
		match = re.match("^\s*<a href=\"/view\.php\?nzbid=(\d+)\".*", curLine)
		if not match:
			continue
		nzbID = match.group(1)
	
	if not nzbID:
		logger.log("Unable to find an NZB ID on the request page "+nzb.url, logger.ERROR)
		return False	
	
	logger.log("Saving to " + fileName, logger.DEBUG)

	urllib.urlretrieve(nzbDownloadURL + nzbID, fileName)

	return True
	
	
def findEpisode (episode, forceQuality=None, manualSearch=False):

	if episode.status == DISCBACKLOG:
		logger.log("Bin-Req doesn't support disc backlog. Use newzbin or download it manually from Bin-Req")
		return []

	logger.log("Searching Bin-Req for " + episode.prettyName(True))

	if forceQuality != None:
		epQuality = forceQuality
	elif episode.show.quality == BEST:
		epQuality = ANY
	else:
		epQuality = episode.show.quality
	
	myCache = BinReqCache()
	myCache.updateCache()
	
	cacheResults = myCache.searchCache(episode.show, episode.season, episode.episode, epQuality)
	logger.log("Cache results: "+str(cacheResults), logger.DEBUG)

	nzbResults = []

	for curResult in cacheResults:
		
		title = curResult["name"]
		url = curResult["url"]
	
		logger.log("Found result " + title + " at " + url)

		result = classes.NZBSearchResult(episode)
		result.provider = providerName.lower()
		result.url = url 
		result.extraInfo = [title]
		result.quality = epQuality
		
		nzbResults.append(result)

	return nzbResults
		

def findPropers(date=None):

	results = BinReqCache().listPropers(date)
	
	return [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time'])) for x in results]

class BinReqCache(tvcache.TVCache):
	
	def __init__(self):

		# only poll Bin-Req every 15 minutes max
		self.minTime = 15
		
		tvcache.TVCache.__init__(self, providerName.lower())
	
	def updateCache(self):

		if not self.shouldUpdate():
			return
		
		url = 'http://www.bin-req.net/rss.php?'
		urlArgs = {'id': 3}

		url += urllib.urlencode(urlArgs)
		
		logger.log("Bin-Req cache update URL: "+ url, logger.DEBUG)
		
		data = getBinReqURL(url)
		
		# as long as the http request worked we count this as an update
		if data:
			self.setLastUpdate()
		
		# now that we've loaded the current RSS feed lets delete the old cache
		logger.log("Clearing cache and updating with new information")
		self._clearCache()
		
		if data == 'Invalid Link':
			raise exceptions.AuthException("Your UID/hash for Bin-Req is incorrect.")
		
		try:
			responseSoup = etree.ElementTree(etree.XML(data))
			items = responseSoup.getiterator('item')
		except Exception, e:
			logger.log("Error trying to load Bin-Req RSS feed: "+str(e), logger.ERROR)
			return []
			
		for item in items:

			title = item.findtext('title')
			url = item.findtext('link')

			if not title or not url:
				logger.log("The XML returned from the Bin-Req RSS feed is incomplete, this result is unusable: "+data, logger.ERROR)
				continue
			
			url = url.replace('view.php', 'download.php')
			
			if "subpack" in title.lower():
				logger.log("This result appears to be a subtitle pack, ignoring: "+title, logger.ERROR)
				continue
			
			url = url.replace('&amp;','&')

			logger.log("Adding item from RSS to cache: "+title, logger.DEBUG)			

			self._addCacheEntry(title, url)

