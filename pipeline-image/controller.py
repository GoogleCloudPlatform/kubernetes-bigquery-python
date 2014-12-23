
import os

script = os.environ['PROCESSINGSCRIPT']

if script == 'redis-to-bigquery':
  os.system("python redis-to-bigquery.py")
elif script == 'twitter-to-redis':
  os.system("python twitter-to-redis.py")
else:
  print "unknown script %s" % script
