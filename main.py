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
import lib.cloudstorage as gcs
import logging
# from google.appengine.api import app_identity
from datetime import datetime

import secrets
from database.gcs_file import GCSFile


my_default_retry_params = gcs.RetryParams(initial_delay=0.2,
                                          max_delay=5.0,
                                          backoff_factor=2,
                                          max_retry_period=15)
gcs.set_default_retry_params(my_default_retry_params)


template_dir = os.path.join(os.path.dirname(__file__), '')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True, variable_start_string='@|', variable_end_string='|@')

if os.environ.get('SERVER_SOFTWARE','').startswith('Development'):
    DEBUG = True
else:
    DEBUG = False

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
            self.approved_origins = ['https://deepspace9.firebaseapp.com', 'http://localhost:9000']

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
        reportFile = self.get_uploads('file_input')
        blob_info = reportFile[0]
        # str(blob_info.key())
        self.render_json({'status': 'success', 'blobKey': str(blob_info.key())})

    def options(self):
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET'

class BlobStoreDemo(BaseHandler, blobstore_handlers.BlobstoreUploadHandler):
    def get(self):
        upload_url = blobstore.create_upload_url('/blobstore')
        self.render('templates/blobstore-demo.html', upload_url=upload_url)


class GCS(BaseHandler):
    def initialize(self, *a, **kw):
        BaseHandler.initialize(self, *a, **kw)
        if self.request.headers.get('Origin') and self.request.headers.get('Origin') in self.approved_origins:
            self.response.headers.add_header('Access-Control-Allow-Origin', self.request.headers['Origin'])

    def options(self):
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET'

    def get(self):
        file_id = self.request.get('fileId')
        # stat = gcs.stat(file_name)
        if file_id and file_id.isdigit():
            # get the gcs_file_name from the database
            db_gcs_file = GCSFile.get(int(file_id))
            if db_gcs_file:
                # check if it exists in gcs
                try:
                    stat = gcs.stat(db_gcs_file.gcs_file_name)
                except gcs.NotFoundError:
                    self.response.set_status(404)
                    self.write('404: This file does not exist')
                else:
                    # return it if it does
                    gcs_file = gcs.open(db_gcs_file.gcs_file_name)
                    self.response.headers['Content-Type'] = stat.content_type
                    self.response.headers['Content-Disposition'] = "attachment; filename=" + stat.metadata[
                        'x-goog-meta-original-name']
                    self.response.write(gcs_file.read())
                    gcs_file.close()
            else:
                self.response.set_status(404)
                self.write('404: This file does not exist')

    def post(self):
        reportFile = self.request.POST['file_input']
        folder_name = self.request.get('folderName')
        user_name = self.request.get('userName')
        user_id = self.request.get('userId')

        if not reportFile.filename or not folder_name or not user_name or not user_id:
            self.response.set_status(400)
            self.render_json({'reason': 'Not all required parameters found', 'status': 'error'})
            return


        bucket_name = os.environ.get('BUCKET_NAME', 'deepspace9-1134.appspot.com')
        bucket = '/' + bucket_name + '/' + folder_name
        filename = bucket + '/' + reportFile.filename

        # Check if the file already exists in google cloud storage
        exists = True
        try:
            gcs.stat(filename)
        except gcs.NotFoundError:
            exists = False

        if exists:
            # find it in the database and get its key
            files = GCSFile.get_by_gcs_file_name(filename)
            if len(files) == 1:
                db_gcs_file = files[0]
                db_gcs_file.user_id = user_id
                db_gcs_file.user_name = user_name
                db_gcs_file.original_file_name = reportFile.filename
                db_gcs_file.gcs_file_name = filename
                db_gcs_file.timestamp = datetime.now()
                logging.error(db_gcs_file.key.id())
            else:
                self.response.set_status(500)
                self.render_json({'status': 'error', 'key': '', 'reason': 'Unexpected number of files found in the database'})
                return
        else:
            # write a new entry in the DB
            db_gcs_file = GCSFile.save_new(user_id=user_id, user_name=user_name, original_file_name=reportFile.filename,
                                        gcs_file_name=filename)
        # save to database
        db_gcs_file.put()

        # write the file to GCS
        write_retry_params = gcs.RetryParams(backoff_factor=1.1)
        gcs_file = gcs.open(filename,
                            'w',
                            content_type=reportFile.type,
                            options={'x-goog-meta-user-name': user_name,
                                     'x-goog-meta-user-id': user_id,
                                     'x-goog-meta-original-name': str(reportFile.filename)},
                            retry_params=write_retry_params)
        gcs_file.write(reportFile.value)
        gcs_file.close()
        # # reply to the app with success and the key
        self.render_json({'status': 'success', 'key': db_gcs_file.key.urlsafe(), 'id': db_gcs_file.key.id()})


class GCSDemo(BaseHandler):
    def initialize(self, *a, **kw):
        BaseHandler.initialize(self, *a, **kw)
        if self.request.headers.get('Origin') and self.request.headers.get('Origin') in self.approved_origins:
            self.response.headers.add_header('Access-Control-Allow-Origin', self.request.headers['Origin'])

    def options(self):
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET'

    def get(self):
        self.render('templates/gcs-demo.html')

    def post(self):
        reportFile = self.request.POST['file_input']
        folder_name = self.request.get('folderName')
        bucket_name = os.environ.get('BUCKET_NAME',
                                     'deepspace9-1134.appspot.com')

        # self.response.headers['Content-Type'] = 'text/plain'
        # self.response.write('Demo GCS Application running from Version: '
        #                     + os.environ['CURRENT_VERSION_ID'] + '\n')
        # self.response.write('Using bucket name: ' + bucket_name + '\n\n')

        bucket = '/' + bucket_name + '/' + folder_name
        filename = bucket + '/' + reportFile.filename

        """Create a file.

        The retry_params specified in the open call will override the default
        retry params for this particular file handle.

        Args:
          filename: filename.
        """
        # self.response.write('Creating file %s\n' % filename)

        write_retry_params = gcs.RetryParams(backoff_factor=1.1)
        gcs_file = gcs.open(filename,
                            'w',
                            content_type=reportFile.type,
                            options={'x-goog-meta-foo': 'foo',
                                     'x-goog-meta-bar': 'bar'},
                            retry_params=write_retry_params)
        gcs_file.write(reportFile.value)
        gcs_file.close()
        # # echo the file back
        gcs_file = gcs.open(filename)
        self.response.headers['Content-Type'] = reportFile.type
        self.response.headers['Content-Disposition'] = "attachment; filename=" + str(reportFile.filename)
        self.response.write(gcs_file.read())
        gcs_file.close()


class GCSGitDemo(BaseHandler):
    """Main page for GCS demo application."""

    def get(self):
        bucket_name = os.environ.get('BUCKET_NAME',
                                     'deepspace9-1134.appspot.com')

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Demo GCS Application running from Version: '
                            + os.environ['CURRENT_VERSION_ID'] + '\n')
        self.response.write('Using bucket name: ' + bucket_name + '\n\n')

        bucket = '/' + bucket_name
        filename = bucket + '/demo-testfile'
        self.tmp_filenames_to_clean_up = []

        try:
            self.create_file(filename)
            self.response.write('\n\n')

            self.read_file(filename)
            self.response.write('\n\n')

            self.stat_file(filename)
            self.response.write('\n\n')

            # self.create_files_for_list_bucket(bucket)
            # self.response.write('\n\n')
            #
            # self.list_bucket(bucket)
            # self.response.write('\n\n')
            #
            # self.list_bucket_directory_mode(bucket)
            # self.response.write('\n\n')

        except Exception, e:
            logging.exception(e)
            self.delete_files()
            self.response.write('\n\nThere was an error running the demo! '
                                'Please check the logs for more details.\n')

        else:
            self.delete_files()
            self.response.write('\n\nThe demo ran successfully!\n')

    def create_file(self, filename):

        """Create a file.

        The retry_params specified in the open call will override the default
        retry params for this particular file handle.

        Args:
          filename: filename.
        """
        self.response.write('Creating file %s\n' % filename)

        write_retry_params = gcs.RetryParams(backoff_factor=1.1)
        gcs_file = gcs.open(filename,
                            'w',
                            content_type='text/plain',
                            options={'x-goog-meta-foo': 'foo',
                                     'x-goog-meta-bar': 'bar'},
                            retry_params=write_retry_params)
        gcs_file.write('abcde\n')
        gcs_file.write('f' * 1024 * 4 + '\n')
        gcs_file.close()
        self.tmp_filenames_to_clean_up.append(filename)


    def read_file(self, filename):
        self.response.write('Abbreviated file content (first line and last 1K):\n')

        gcs_file = gcs.open(filename)
        self.response.write(gcs_file.readline())
        gcs_file.seek(-1024, os.SEEK_END)
        self.response.write(gcs_file.read())
        gcs_file.close()


    def stat_file(self, filename):
        self.response.write('File stat:\n')

        stat = gcs.stat(filename)
        self.response.write(repr(stat))


    def create_files_for_list_bucket(self, bucket):
        self.response.write('Creating more files for listbucket...\n')
        filenames = [bucket + n for n in ['/foo1', '/foo2', '/bar', '/bar/1',
                                          '/bar/2', '/boo/']]
        for f in filenames:
            self.create_file(f)


    def list_bucket(self, bucket):
        """Create several files and paginate through them.

        Production apps should set page_size to a practical value.

        Args:
          bucket: bucket.
        """
        self.response.write('Listbucket result:\n')

        page_size = 1
        stats = gcs.listbucket(bucket + '/foo', max_keys=page_size)
        while True:
            count = 0
            for stat in stats:
                count += 1
                self.response.write(repr(stat))
                self.response.write('\n')

            if count != page_size or count == 0:
                break
            stats = gcs.listbucket(bucket + '/foo', max_keys=page_size,
                                   marker=stat.filename)


    def list_bucket_directory_mode(self, bucket):
        self.response.write('Listbucket directory mode result:\n')
        for stat in gcs.listbucket(bucket + '/b', delimiter='/'):
            self.response.write('%r' % stat)
            self.response.write('\n')
            if stat.is_dir:
                for subdir_file in gcs.listbucket(stat.filename, delimiter='/'):
                    self.response.write('  %r' % subdir_file)
                    self.response.write('\n')


    def delete_files(self):
        self.response.write('Deleting files...\n')
        for filename in self.tmp_filenames_to_clean_up:
            self.response.write('Deleting file %s\n' % filename)
            try:
                gcs.delete(filename)
            except gcs.NotFoundError:
                pass


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

class NDBDemo(BaseHandler):
    def get(self):
        self.render('templates/ndb-demo.html')

    def post(self):
        self.response.headers['Content-Type'] = 'text/plain'
        user_id = self.request.get('userId')
        user_name = self.request.get('userName')
        original_file_name = 'original'
        gcs_file_name = 'oh yeahs'
        new_file = GCSFile.save_new(user_id=user_id, user_name=user_name, original_file_name=original_file_name, gcs_file_name=gcs_file_name)
        new_file.put()
        self.write('success\n')
        self.write('Here is the new key \n')
        self.write(new_file.key.urlsafe())
        urlsafe_key = new_file.key.urlsafe()
        # echo back the file
        self.response.write('\\n')
        echo_file = GCSFile.get(urlsafe_key)
        self.write(echo_file.user_name)

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/sign_s3', SignS3),
    ('/s3-demo', S3_Demo),
    ('/blobstore', BlobStore),
    ('/blobstore-demo', BlobStoreDemo),
    ('/gcs-git-demo', GCSGitDemo),
    ('/gcs-demo', GCSDemo),
    ('/ndb-demo', NDBDemo),
    ('/gcs', GCS),
], debug=DEBUG)
