import sys
import time
import re
import os
import urllib2
import httplib
import unittest
import md5

import StringIO

__version__ = (0,1)
__author__ = "Staffan Malmgren <staffan@tomtebo.org>"


class ThrottlingProcessor(urllib2.BaseHandler):
    """Prevents overloading the remote web server by delaying requests.

    Causes subsequent requests to the same web server to be delayed
    a specific amount of seconds. The first request to the server
    always gets made immediately"""
    __shared_state = {}
    def __init__(self,throttleDelay=5):
        """The number of seconds to wait between subsequent requests"""
        # Using the Borg design pattern to achieve shared state
        # between object instances:
        self.__dict__ = self.__shared_state
        self.throttleDelay = throttleDelay
        if not hasattr(self,'lastRequestTime'):
            self.lastRequestTime = {}
        
    def default_open(self,request):
        currentTime = time.time()
        if ((request.host in self.lastRequestTime) and
            (time.time() - self.lastRequestTime[request.host] < self.throttleDelay)):
            self.throttleTime = (self.throttleDelay -
                                 (currentTime - self.lastRequestTime[request.host]))
            # print "ThrottlingProcessor: Sleeping for %s seconds" % self.throttleTime
            time.sleep(self.throttleTime)
        self.lastRequestTime[request.host] = currentTime

        return None

    def http_response(self,request,response):
        if hasattr(self,'throttleTime'):
            response.info().addheader("x-throttling", "%s seconds" % self.throttleTime)
            del(self.throttleTime)
        return response

class CacheHandler(urllib2.BaseHandler):
    """Stores responses in a persistant on-disk cache.

    If a subsequent GET request is made for the same URL, the stored
    response is returned, saving time, resources and bandwith"""
    def __init__(self,cacheLocation):
        """The location of the cache directory"""
        self.cacheLocation = cacheLocation
        if not os.path.exists(self.cacheLocation):
            os.mkdir(self.cacheLocation)
            
    def default_open(self,request):
        if ((request.get_method() == "GET") and 
            (CachedResponse.ExistsInCache(self.cacheLocation, request.get_full_url()))):
            # print "CacheHandler: Returning CACHED response for %s" % request.get_full_url()
            return CachedResponse(self.cacheLocation, request.get_full_url(), setCacheHeader=True)	
        else:
            return None # let the next handler try to handle the request

    def http_response(self, request, response):
        if request.get_method() == "GET":
            if 'x-cache' not in response.info():
                CachedResponse.StoreInCache(self.cacheLocation, request.get_full_url(), response)
                return CachedResponse(self.cacheLocation, request.get_full_url(), setCacheHeader=False)
            else:
                return CachedResponse(self.cacheLocation, request.get_full_url(), setCacheHeader=True)
        else:
            return response
    
class CachedResponse(StringIO.StringIO):
    """An urllib2.response-like object for cached responses.

    To determine wheter a response is cached or coming directly from
    the network, check the x-cache header rather than the object type."""
    
    def ExistsInCache(cacheLocation, url):
        hash = md5.new(url).hexdigest()
        return (os.path.exists(cacheLocation + os.sep + hash + ".headers") and 
                os.path.exists(cacheLocation + os.sep + hash + ".body"))
    ExistsInCache = staticmethod(ExistsInCache)

    def StoreInCache(cacheLocation, url, response):
        hash = md5.new(url).hexdigest()
        f = open(cacheLocation + os.sep + hash + ".headers", "w")
        headers = str(response.info())
        f.write(headers)
        f.close()
        f = open(cacheLocation + os.sep + hash + ".body", "w")
        f.write(response.read())
        f.close()
    StoreInCache = staticmethod(StoreInCache)
    
    def __init__(self, cacheLocation,url,setCacheHeader=True):
        self.cacheLocation = cacheLocation
        hash = md5.new(url).hexdigest()
        StringIO.StringIO.__init__(self, file(self.cacheLocation + os.sep + hash+".body").read())
        self.url     = url
        self.code    = 200
        self.msg     = "OK"
        headerbuf = file(self.cacheLocation + os.sep + hash+".headers").read()
        if setCacheHeader:
            headerbuf += "x-cache: %s/%s\r\n" % (self.cacheLocation,hash)
        self.headers = httplib.HTTPMessage(StringIO.StringIO(headerbuf))

    def info(self):
        return self.headers
    def geturl(self):
        return self.url