# Copyright 2012 Google Inc. All Rights Reserved.
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

import getopt
import sys

from gslib.command import Command
from gslib.command import COMMAND_NAME
from gslib.command import COMMAND_NAME_ALIASES
from gslib.command import FILE_URIS_OK
from gslib.command import MAX_ARGS
from gslib.command import MIN_ARGS
from gslib.command import PROVIDER_URIS_OK
from gslib.command import SUPPORTED_SUB_ARGS
from gslib.command import URIS_START_ARG
from gslib.exception import CommandException
from gslib.help_provider import CreateHelpText
from gslib.help_provider import HELP_NAME
from gslib.help_provider import HELP_NAME_ALIASES
from gslib.help_provider import HELP_ONE_LINE_SUMMARY
from gslib.help_provider import HELP_TEXT
from gslib.help_provider import HelpType
from gslib.help_provider import HELP_TYPE
from gslib.help_provider import SUBCOMMAND_HELP_TEXT
from gslib.util import NO_MAX
from gslib.util import UnaryDictToXml
from xml.dom.minidom import parseString as XmlParseString


_SET_SYNOPSIS = """
  gsutil web set [-m main_page_suffix] [-e error_page] bucket_uri...
"""

_GET_SYNOPSIS = """
  gsutil web get bucket_uri
"""

_SYNOPSIS = _SET_SYNOPSIS + _GET_SYNOPSIS.lstrip('\n')

_SET_DESCRIPTION = """
<B>SET</B>
  The "gsutil web set" command will allow you to set Website Configuration
  on your bucket(s). The "set" sub-command has the following options:

<B>SET OPTIONS</B>
  -m <index.html>      Specifies the object name to serve when a bucket
                       listing is requested via the CNAME alias to
                       c.storage.googleapis.com.

  -e <404.html>        Specifies the error page to serve when a request is made
                       for a non-existent object via the CNAME alias to
                       c.storage.googleapis.com.

"""

_GET_DESCRIPTION = """
<B>GET</B>
  The "gsutil web get" command will gets the web semantics configuration for
  a bucket and displays an XML representation of the configuration.

  In Google Cloud Storage, this would look like:

    <?xml version="1.0" ?>
    <WebsiteConfiguration>
      <MainPageSuffix>
        index.html
      </MainPageSuffix>
      <NotFoundPage>
        404.html
      </NotFoundPage>
    </WebsiteConfiguration>

"""

_DESCRIPTION = """
  The Website Configuration feature enables you to configure a Google Cloud
  Storage bucket to behave like a static website. This means requests made via a
  domain-named bucket aliased using a Domain Name System "CNAME" to
  c.storage.googleapis.com will work like any other website, i.e., a GET to the
  bucket will serve the configured "main" page instead of the usual bucket
  listing and a GET for a non-existent object will serve the configured error
  page.

  For example, suppose your company's Domain name is example.com. You could set
  up a website bucket as follows:

  1. Create a bucket called example.com (see the "DOMAIN NAMED BUCKETS"
     section of "gsutil help naming" for details about creating such buckets).

  2. Create index.html and 404.html files and upload them to the bucket.

  3. Configure the bucket to have website behavior using the command:

       gsutil web set -m index.html -e 404.html gs://example.com

  4. Add a DNS CNAME record for example.com pointing to c.storage.googleapis.com
     (ask your DNS administrator for help with this).

  Now if you open a browser and navigate to http://example.com, it will display
  the main page instead of the default bucket listing. Note: It can take time
  for DNS updates to propagate because of caching used by the DNS, so it may
  take up to a day for the domain-named bucket website to work after you create
  the CNAME DNS record.

  Additional notes:

  1. Because the main page is only served when a bucket listing request is made
     via the CNAME alias, you can continue to use "gsutil ls" to list the bucket
     and get the normal bucket listing (rather than the main page).

  2. The main_page_suffix applies to each subdirectory of the bucket. For
     example, with the main_page_suffix configured to be index.html, a GET
     request for http://example.com would retrieve
     http://example.com/index.html, and a GET request for
     http://example.com/photos would retrieve
     http://example.com/photos/index.html.

  2. There is just one 404.html page: For example, a GET request for
     http://example.com/photos/missing would retrieve
     http://example.com/404.html, not http://example.com/photos/404.html.

  3. For additional details see
     https://developers.google.com/storage/docs/website-configuration.

  The web command has two sub-commands:
""" + _SET_DESCRIPTION + _GET_DESCRIPTION

_detailed_help_text = CreateHelpText(_SYNOPSIS, _DESCRIPTION)

_get_help_text = CreateHelpText(_GET_SYNOPSIS, _GET_DESCRIPTION)
_set_help_text = CreateHelpText(_SET_SYNOPSIS, _SET_DESCRIPTION)


def BuildGSWebConfig(main_page_suffix=None, not_found_page=None):
  config_body_l = ['<WebsiteConfiguration>']
  if main_page_suffix:
    config_body_l.append('<MainPageSuffix>%s</MainPageSuffix>' %
                         main_page_suffix)
  if not_found_page:
    config_body_l.append('<NotFoundPage>%s</NotFoundPage>' %
                         not_found_page)
  config_body_l.append('</WebsiteConfiguration>')
  return "".join(config_body_l)

def BuildS3WebConfig(main_page_suffix=None, error_page=None):
  config_body_l = ['<WebsiteConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">']
  if not main_page_suffix:
      raise CommandException('S3 requires main page / index document')
  config_body_l.append('<IndexDocument><Suffix>%s</Suffix></IndexDocument>' %
                       main_page_suffix)
  if error_page:
    config_body_l.append('<ErrorDocument><Key>%s</Key></ErrorDocument>' %
                         error_page)
  config_body_l.append('</WebsiteConfiguration>')
  return "".join(config_body_l)

class WebCommand(Command):
  """Implementation of gsutil web command."""

  # Command specification (processed by parent class).
  command_spec = {
    # Name of command.
    COMMAND_NAME : 'web',
    # List of command name aliases.
    COMMAND_NAME_ALIASES : ['setwebcfg', 'getwebcfg'],
    # Min number of args required by this command.
    MIN_ARGS : 2,
    # Max number of args required by this command, or NO_MAX.
    MAX_ARGS : NO_MAX,
    # Getopt-style string specifying acceptable sub args.
    SUPPORTED_SUB_ARGS : 'm:e:',
    # True if file URIs acceptable for this command.
    FILE_URIS_OK : False,
    # True if provider-only URIs acceptable for this command.
    PROVIDER_URIS_OK : False,
    # Index in args of first URI arg.
    URIS_START_ARG : 1,
  }
  help_spec = {
    # Name of command or auxiliary help info for which this help applies.
    HELP_NAME : 'web',
    # List of help name aliases.
    HELP_NAME_ALIASES : ['getwebcfg', 'setwebcfg'],
    # Type of help)
    HELP_TYPE : HelpType.COMMAND_HELP,
    # One line summary of this help.
    HELP_ONE_LINE_SUMMARY : 'Set a main page and/or error page for one or more buckets',
    # The full help text.
    HELP_TEXT : _detailed_help_text,
    # Help text for sub-commands.
    SUBCOMMAND_HELP_TEXT : {'get' : _get_help_text,
                            'set' : _set_help_text},
  }
  
  def _GetWeb(self):
    uri_args = self.args

    # Iterate over URIs, expanding wildcards, and getting the website
    # configuration on each.
    some_matched = False
    for uri_str in uri_args:
      for blr in self.WildcardIterator(uri_str):
        uri = blr.GetUri()
        if not uri.names_bucket():
          raise CommandException('URI %s must name a bucket for the %s command'
                                 % (uri, self.command_name))
        some_matched = True
        sys.stderr.write('Getting website config on %s...\n' % uri)
        web_config_xml = UnaryDictToXml(uri.get_website_config())
        sys.stdout.write(XmlParseString(web_config_xml).toprettyxml())
    if not some_matched:
      raise CommandException('No URIs matched')

  def _SetWeb(self):
    main_page_suffix = None
    error_page = None
    if self.sub_opts:
      for o, a in self.sub_opts:
        if o == '-m':
          main_page_suffix = a
        elif o == '-e':
          error_page = a

    uri_args = self.args

    # Iterate over URIs, expanding wildcards, and setting the website
    # configuration on each.
    some_matched = False
    for uri_str in uri_args:
      for blr in self.WildcardIterator(uri_str):
        uri = blr.GetUri()
        if not uri.names_bucket():
          raise CommandException('URI %s must name a bucket for the %s command'
                                 % (str(uri), self.command_name))
        some_matched = True
        self.logger.info('Setting website config on %s...', uri)
        uri.set_website_config(main_page_suffix, error_page)
    if not some_matched:
      raise CommandException('No URIs matched')

  # Command entry point.
  def RunCommand(self):
    action_subcommand = self.args.pop(0)
    (self.sub_opts, self.args) = getopt.getopt(self.args,
          self.command_spec[SUPPORTED_SUB_ARGS])
    self.CheckArguments()
    if action_subcommand == 'get':
      func = self._GetWeb
    elif action_subcommand == 'set':
      func = self._SetWeb
    else:
      raise CommandException(('Invalid subcommand "%s" for the %s command.\n'
                             'See "gsutil help web".') %
                             (action_subcommand, self.command_name))
    func()
    return 0
