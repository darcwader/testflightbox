import argparse
import boto3 as boto
import errno
import os
import pathlib
import plistlib
import re
import sys
import threading
import zipfile
import requests

parser = argparse.ArgumentParser()

parser.add_argument("--ipa",required=True, help="IPA file")
parser.add_argument("--name", required=True, help="app name, folder for OTA")
parser.add_argument("--build", required=True, type=int, help="build number")

class ProgressPercentage(object):
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
    def __call__(self, bytes_amount):
        # To simplify we'll assume this is hooked up
        # to a single filename.
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            sys.stdout.write(
                "\rUploading ipa %s  %s / %s  (%.2f%%)" % (
                    self._filename, self._seen_so_far, self._size,
                    percentage))
            sys.stdout.flush()

def shorten(uri):
    query_params = {
        'access_token': os.environ['BITLY_ACCESS_TOKEN'],
        'longUrl': uri
    }

    endpoint = 'https://api-ssl.bitly.com/v3/shorten'
    response = requests.get(endpoint, params=query_params, verify=False)

    data = response.json()


    if not data['status_code'] == 200:
        logger.error("Unexpected status_code: {} in bitly response. {}".format(data['status_code'], response.text))

    return data['data']['url']

if __name__ == "__main__":
    args = parser.parse_args()

    archive = zipfile.ZipFile(args.ipa)
    plist_file = list(filter(lambda x: re.search('.app/Info.plist', x) != None , archive.namelist()))[0]
    #print("Found plist {}".format(plist_file))

    read = None
    try:
        with archive.open(plist_file, 'r') as fh:
            read = fh.read()
    except:
        print("error reading info plist file")
        sys.exit(0)

    info = None
    try:
        info = plistlib.readPlistFromBytes(read)
    except:
        print("error parsing plist")
        sys.exit(0)


    try:
        app_title = info['CFBundleDisplayName']
        app_identifier = info['CFBundleIdentifier']
    except:
        print("exception reading app_title, bundle identifier")
        sys.exit(0)

    print("App Name: {}".format(app_title))
    print("Bundle Identifier: {}".format(app_identifier))


    template_plist = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>items</key>
        <array>
            <dict>
                <key>assets</key>
                <array>
                    <dict>
                        <key>kind</key>
                        <string>software-package</string>
                        <key>url</key>
                        <string>https://builds-ymedialabs.s3.amazonaws.com/{}/{}/{}.ipa</string>
                    </dict>
                </array>
                <key>metadata</key>
                <dict>
                    <key>bundle-identifier</key>
                    <string>{}</string>
                    <key>bundle-version</key>
                    <string>1.0</string>
                    <key>kind</key>
                    <string>software</string>
                    <key>title</key>
                    <string>{}</string>
                </dict>
            </dict>
        </array>
    </dict>
</plist>
    """
    template_plist_format = template_plist.format(args.name, args.build, args.name, app_identifier, app_title)


    template_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<title>{} Prototype</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/css/bootstrap.min.css">
<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.12.2/jquery.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/js/bootstrap.min.js"></script>
</head>
<body>

<div class="container">
    <h2>{}</h2>
    <h3>Build {}</h3>
    <br/><br/>
    <a href="itms-services://?action=download-manifest&url=https://builds-ymedialabs.s3.amazonaws.com/{}/{}/{}.plist" class="btn btn-info btn-lg btn-block" role="button">Install</a>
    <br/>
    <br/>
    <p>If you are getting untrusted alert, please follow the following steps</p><br/>
    <img src="https://dl.dropboxusercontent.com/s/n7d7au606ihb1vo/mdc.gif"></img>
</div>
</body>
</html>
    """
    template_html_format = template_html.format(args.name, args.name, args.build, args.name, args.build, args.name)

    url_plist = "{}/{}/{}.plist".format(args.name, args.build, args.name)
    url_ipa = "{}/{}/{}.ipa".format(args.name, args.build, args.name)
    url_html = "{}/{}/{}.html".format(args.name, args.build, args.name)
    print(url_plist, url_ipa, url_html)


    s3 = boto.resource('s3')
    builds = s3.Bucket('builds-ymedialabs')

    print("Uploading Plist...", end='')
    builds.put_object('public-read',Body=template_plist_format,ContentType="application/x-plist", Key=url_plist)
    print("Done")

    print("Uploading html...",end='')
    builds.put_object('public-read',Body=template_html_format,ContentType="text/html", Key=url_html)
    print("Done")

    s3client = boto.client('s3')
    s3client.upload_file(args.ipa, "builds-ymedialabs", url_ipa,Callback=ProgressPercentage(args.ipa))
    print(" Done")


    full_url = "https://builds-ymedialabs.s3.amazonaws.com/{}".format(url_html)
    print("\nOTA full link: {}".format(full_url))

    print("OTA short url: {}".format(shorten(full_url)))



