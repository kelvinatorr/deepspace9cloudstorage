__author__ = 'Kelvin'

from google.appengine.ext import ndb


class GCSFile(ndb.Model):
  gcs_file_name = ndb.StringProperty(required=True)
  user_id = ndb.StringProperty(required=True)
  user_name = ndb.StringProperty(required=True)
  original_file_name = ndb.StringProperty(required=True)
  timestamp = ndb.DateTimeProperty(auto_now_add = True)

  @classmethod
  def save_new(cls, gcs_file_name, user_id, user_name, original_file_name):
    parent = ndb.Key('App', 'deepSpace9')
    return cls(parent=parent, user_id=user_id, user_name=user_name, original_file_name=original_file_name, gcs_file_name=gcs_file_name)

  @classmethod
  def get(cls, urlsafe_key):
    key = ndb.Key(urlsafe=urlsafe_key)
    return key.get()

  @classmethod
  def get_by_gcs_file_name(cls, gcs_file_name):
    files = cls.query(cls.gcs_file_name == gcs_file_name)
    return list(files)
    # if file:
    #   return True
    # else:
    #   return False
