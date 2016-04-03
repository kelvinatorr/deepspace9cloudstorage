__author__ = 'Kelvin'

from google.appengine.ext import ndb


class FileDeletes(ndb.Model):
  gcs_file_name = ndb.StringProperty(required=True)
  user_id = ndb.StringProperty(required=True)
  original_file_name = ndb.StringProperty(required=True)
  timestamp = ndb.DateTimeProperty(auto_now_add = True)

  @classmethod
  def save_new(cls, gcs_file_name, user_id, original_file_name):
    parent = ndb.Key('App', 'deepSpace9')
    return cls(parent=parent, user_id=user_id, original_file_name=original_file_name, gcs_file_name=gcs_file_name)