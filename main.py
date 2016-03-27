#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
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
#
import webapp2
import jinja2
from hashlib import sha1
import time, os, json, base64, hmac, urllib
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
import secrets
import logging

template_dir = os.path.join(os.path.dirname(__file__), '')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True, variable_start_string='@|', variable_end_string='|@')

if os.environ.get('SERVER_SOFTWARE','').startswith('Development'):
    DEBUG = True

class BaseHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
      t = jinja_env.get_template(template)
      return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        if DEBUG:
            self.approved_origins = ['http://localhost:9000']
        else:
            self.approved_origins = ['https://deepspace9.firebaseapp.com']

    def render_json(self, d):
        json_txt = json.dumps(d)
        self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
        self.write(")]}',\n" + json_txt)


class MainHandler(BaseHandler):
    def get(self):
        # self.write(secrets.test)
        self.render('index.html')

class S3_Demo(BaseHandler):
    def get(self):
        self.render('templates/s3-demo.html')

class BlobStore(BaseHandler, blobstore_handlers.BlobstoreUploadHandler):
    def initialize(self, *a, **kw):
        BaseHandler.initialize(self, *a, **kw)
        if self.request.headers.get('Origin') and self.request.headers.get('Origin') in self.approved_origins:
            self.response.headers.add_header('Access-Control-Allow-Origin', self.request.headers['Origin'])

    def get(self):
        upload_url = blobstore.create_upload_url('/blobstore')
        self.render_json(dict({'uploadUrl': upload_url}))

    def post(self):
        pass

    def options(self):
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET'


# From https://devcenter.heroku.com/articles/s3-upload-python
class SignS3(BaseHandler):
    def get(self):
        AWS_ACCESS_KEY = secrets.AWS_ACCESS_KEY
        AWS_SECRET_KEY = secrets.AWS_SECRET_KEY
        S3_BUCKET = 'deepspace9'

        object_name = urllib.quote_plus(self.request.get('file_name'))
        mime_type = self.request.get('file_type')
        # object_name = urllib.quote_plus(request.args.get('file_name'))
        # mime_type = request.args.get('file_type')

        expires = int(time.time()+60*60*24)
        amz_headers = "x-amz-acl:public-read"

        string_to_sign = "PUT\n\n%s\n%d\n%s\n/%s/%s" % (mime_type, expires, amz_headers, S3_BUCKET, object_name)

        signature = base64.encodestring(hmac.new(AWS_SECRET_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest())
        signature = urllib.quote_plus(signature.strip())

        url = 'https://%s.s3-us-west-2.amazonaws.com/%s' % (S3_BUCKET, object_name)

        content = json.dumps({
            'signed_request': '%s?AWSAccessKeyId=%s&Expires=%s&Signature=%s' % (url, AWS_ACCESS_KEY, expires, signature),
            'url': url,
        })
        self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
        self.write(content)

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/sign_s3', SignS3),
    ('/s3-demo', S3_Demo),
    ('/blobstore', BlobStore)
], debug=DEBUG)
