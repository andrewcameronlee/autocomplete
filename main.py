# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START all]
import cgi
import urllib
import json
import os
import random
import unicodedata
import webapp2
import logging
import cloudstorage

from google.appengine.ext.db import stats
from google.appengine.ext import ndb
from google.appengine.api import search
from google.appengine.api import memcache
from google.appengine.api import app_identity
index = search.Index(name='productsearch')

""" GET /load?file=filename method to index products from JSON file """
class BuildIndex(webapp2.RequestHandler):
    def get(self):
        datafile = os.path.join('data', self.request.get('file') + '.json')
        with open(datafile) as json_data:
            d = json.load(json_data)
            self.importData(d)

    def importData(self, reader):
        BATCH_SIZE = 100
        docs = []
        for row in reader:
            try:
                productname = unicodedata.normalize('NFKD', row['name'].strip()).encode('ascii', 'ignore')
                pid = str(row['sku'])
                docs.append(self.createDocument(pid, productname, random.randint(1,1000)))
            if len(docs) == BATCH_SIZE:
                try:
                    add_results = search.Index(name='productsearch').add(docs)
                except search.Error:
                    print "Problem loading data"
                docs = []

    """ Create a document to be indexed """
    def createDocument(self, pid, name, ranking):
        fields = [
          search.TextField(name='name', value=name),
          search.TextField(name='keywords', value=self.keyWords(name)),
          search.NumberField(name='ranking', value=ranking) ]
        return search.Document(doc_id=pid, fields=fields)

    """ Break the product name into tokens"""
    def keyWords(self, productname):
        keywords = ""
        words = productname.lower().split()
        for word in words:
            keywords += " " + self.subWords(word, 3)
        return keywords

    """ Break a word into tokens: eg apple = app appl apple"""
    def subWords(self, word, minchars):
        retval = ""
        for i in range(minchars,len(word)+1):
            retval += " " + word[:i]
        return retval

""" GET /del remove all products from the index """
class DeleteIndex(webapp2.RequestHandler):
    def get(self):
        try:
          while True:
            document_ids = [document.doc_id
                            for document in index.get_range(ids_only=True)]
            if not document_ids:
              break
            index.delete(document_ids)
        except search.Error:
          logging.exception("Error removing documents:")

""" GET /query?term=product_name """
class Query(webapp2.RequestHandler):
    def get(self):
        query = self.request.get('term').strip()
        print "Query: " + query
        result = memcache.get(query)
        if result is None:
            result = self.searchForProduct("keywords: " + query)
            memcache.add(self.request.get('term'), result, 10000)
        else:
            print "Cache Hit!"
        self.response.headers['Content-Type'] = 'application/json'
        self.response.write(result)

    def searchForProduct(self, queryval):
        sort_ranking = search.SortExpression(
        expression='ranking',
        direction=search.SortExpression.DESCENDING,
        default_value=0)
        sort_options = search.SortOptions(expressions=[sort_ranking])
        query_options = search.QueryOptions(
        limit=5,
        returned_fields=['name'],
        sort_options=sort_options)
        query = search.Query(query_string=queryval, options=query_options)
        outputtxt = ""
        try:
            search_results = index.search(query)
            if (len(search_results.results)):
                outputtxt = '['
                for doc in search_results:
                    outputtxt += '{"name":' + '"' + doc.field("name").value + '"' + '},'
                outputtxt = outputtxt[:-1] + ']'

        except search.Error:
            print "Problem with query"
        print "Result: " + outputtxt
        return outputtxt

class IndexHandler(webapp2.RequestHandler):
  def get(self):
    global_stat = stats.GlobalStat.all().get()
    if (global_stat):
        print 'Total bytes stored: %d' % global_stat.bytes
        print 'Total entities stored: %d' % global_stat.count
    self.response.write("""
    <!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Autocomplete Demo</title>
<link rel="stylesheet" href="static/jquery-ui.css" />
<script src="static/jquery.min.js"></script>
<script src="static/jquery-ui.min.js"></script>
<script>
$(function() {
    $( "#demo" ).autocomplete({
          delay: 300,
          minLength: 3,
          dataType: JSON,
          source: function(request, response) {
          $.ajax({
          url: '/query?term=' + request.term, // <-- API URL is datasource
          success: function(data) {
          response($.map(data, function(item) {
              return {label: item.name};
            }));
          }
          });
          }
    })
});
</script>
</head>
<body>
<p>What are you looking for punk?</p>
<input id="demo" />
</body>
</html>
    """)

app = webapp2.WSGIApplication([
    ('/', IndexHandler),
    ('/query', Query),
    ('/load', BuildIndex),
    ('/del', DeleteIndex)
])
# [END all]
