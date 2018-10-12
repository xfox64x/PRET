# -*- coding: utf-8 -*-

# python standard library
import re, os, sys, urllib2, httplib, ssl

# local pret classes
from helper import output, item

# third party modules
try:
  from pysnmp.entity.rfc3413.oneliner import cmdgen
except ImportError:
  pass

def HTTPResponsePatch(func):
  def inner(*args):
    try:
      return func(*args)
    except httplib.IncompleteRead, e:
      return e.partial
  return inner 
  
httplib.HTTPResponse.read = HTTPResponsePatch(httplib.HTTPResponse.read)

class printerModelDatabase():

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # get the path to the correct database of supported devices
  def get_database_path(self, mode):
    return os.path.join(os.path.join(os.path.dirname(os.path.realpath(__file__)), "db"), (mode + ".dat"))
    
  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # open database of supported devices
  def get_models(self, mode):
    try:
      with open(printerModelDatabase().get_database_path(mode), 'r') as f:
        models = filter(None, (line.strip() for line in f))
      return models
    except IOError as e:
      output().errmsg_("Cannot open file", e)
      return []
    return []
      
  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # get models matching the supplied model, from the database of supported devices
  def get_matching_models(self, mode, model):
    #matches = filter(None, [re.findall(re.escape(m), model, re.I) for m in printerModelDatabase().get_models(mode)])
    #print("Mode:  "+mode)
    #print("Model: "+model)
    #print(matches)
    #return matches
    return filter(None, [re.findall(re.escape(m), model, re.I) for m in printerModelDatabase().get_models(mode)])

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # add model to database of supported devices
  def add_model(self, mode, model):
    if model and len(printerModelDatabase().get_matching_models(mode, model)) == 0 and len(model.strip()) > 0:
      try:
        with open(printerModelDatabase().get_database_path(mode), 'a') as f:
          f.write("%s\n" % str(model))
        return True
        
      except IOError as e:
        output().errmsg_("Cannot open file", e)
        return False
    else:
      return False
  

class capabilities():
  # Hold the supplied mode:
  mode = ""
  
  # Create an array for supported models
  support = []
  
  # Let's not be quick - printers be slow.
  timeout = 5
  
  # set pret.py directory
  rundir = os.path.dirname(os.path.realpath(__file__)) + os.path.sep
  '''
  ┌──────────────────────────────────────────────────────────┐
  │            how to get printer's capabilities?            │
  ├──────┬───────────────────────┬───────────────────────────┤
  │      │ model (for db lookup) │ lang (ps/pjl/pcl support) │
  ├──────┼───────────────────────┼───────────────────────────┤
  │ IPP  │ printer-description   │ printer-description       │
  │ SNMP │ hrDeviceDescr         │ prtInterpreterDescription │
  │ HTTP │ html-title            │ -                         │
  └──────┴───────────────────────┴───────────────────────────┘
  '''

  def __init__(self, args):
    # skip this in unsafe mode
    if not args.safe: return
    
    # Save off the mode argument.
    self.mode = args.mode
    
    # set printer language
    if self.mode == 'ps': lang = ["PS", "PostScript", "BR-Script", "KPDL"]
    if self.mode == 'pjl': lang = ["PJL"]
    if self.mode == 'pcl': lang = ["PCL"]
    
    # get list of PostScript/PJL/PCL capable printers
    self.models = self.get_models(self.mode + ".dat")
    
    # try to get printer capabilities via IPP/SNMP/HTTP
    self.ipp(args.target, lang)
    
    self.http(args.target)
        
    self.snmp(args.target, lang)
    
    # feedback on PostScript/PJL/PCL support
    self.feedback(self.support, lang[0])
    
    # in safe mode, exit if unsupported
    if args.safe and len(self.support) == 0:
      print(os.linesep + "Quitting as we are in safe mode.")
      sys.exit()
    print("")

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # get capabilities via IPP
  def ipp(self, host, lang):
  
    # Define model and langs, from the start, as empty strings.
    model = ""
    langs = ""
    
    sys.stdout.write("Checking for IPP support:         ")
    
    try:
      # poor man's way to get printer info via IPP
      body = ("\x01\x01\x00\x0b\x00\x01\xab\x10\x01G\x00\x12attributes-charset\x00\x05utf-8H"
            + "\x00\x1battributes-natural-language\x00\x02enE\x00\x0bprinter-uri\x00\x14ipp:"
            + "//localhost/ipp/D\x00\x14requested-attributes\x00\x13printer-description\x03")
            
      request  = urllib2.Request("http://" + host + ":631/", data=body, headers={'Content-type': 'application/ipp'})
      
      # Manually doubling  the timeout because this seems to take a while for the printers that it works on.
      # Added SSL context that should avoid validating any printer certificates, just in case connection upgrading happens.
      response = urllib2.urlopen(request, timeout=(self.timeout * 2), context=ssl._create_unverified_context()).read()
      
      # get name of device using regex. Now checking if the regex is successful before assuming it was.
      modelRegexResults = item(re.findall("MDL:(.+?);", response)) # e.g. MDL:hp LaserJet 4250
      if modelRegexResults and modelRegexResults != "":
        model = modelRegexResults
      
      # get language support. Now checking if the regex is successful before assuming it was.
      languageRegexResults = item(re.findall("CMD:(.+?);", response)) # e.g. CMD:PCL,PJL,POSTSCRIPT
      if languageRegexResults and languageRegexResults != "":
        langs = languageRegexResults
      
      # Not really sure what the point of this line is - the data set doesn't really get used, making langs and lang pointless.
      # It's only there to maintain the fact that some variant of PS was found, but it probably shouldn't mix with the other data.
      languageCheck = filter(None, [re.findall(re.escape(pdl), langs, re.I) for pdl in lang])
      if len(languageCheck) > 0:
        self.support += languageCheck
      
      if self.set_support(model):
        output().green_("found [%s]" % (model))
      else:
        output().errmsg_("not found", "check successful but no data")
      
    except Exception as e:
      output().errmsg_("not found", e)

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # get capabilities via HTTP
  def http(self, host):
    sys.stdout.write("Checking for HTTP support:        ")
      
    try:
      # Get the first 5k bytes of the printer config page and hope that the title is in it.
      # Urllib was failing to get all of some config pages and would return a random section of content from the specified page...
      # Added SSL context that should avoid validating any printer certificates, just in case connection upgrading happens.
      html = urllib2.urlopen("http://" + host, timeout=self.timeout, context=ssl._create_unverified_context()).read(5000)
      
      # I'm not entirely sure what this original comment meant, but Regex is the way to go.
      titleMatchObj = re.search("<title.*?>\s*(?P<TitleGroup>[a-zA-Z0-9 \.-_/]+).*?</title>", html, re.I|re.M|re.S)
      
      # Also more validation and better discovery.
      if titleMatchObj:
        # get name of device and check for language support
        self.set_support(titleMatchObj.group("TitleGroup"))
        output().green_("found [%s]" % (titleMatchObj.group("TitleGroup")))
      else:
        output().errmsg_("not found", "check successful but no data")
      
    except Exception as e:
      output().errmsg_("not found", e)

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # get capabilities via SNMP
  def snmp(self, host, lang):
    sys.stdout.write("Checking for SNMP support:        ")
    
    try:
      # query device description and supported languages
      desc, desc_oid = [], '1.3.6.1.2.1.25.3.2.1.3'    # HOST-RESOURCES-MIB → hrDeviceDescr
      pdls, pdls_oid = [], '1.3.6.1.2.1.43.15.1.1.5.1' # Printer-MIB → prtInterpreterDescription
      
      error, error_status, idx, binds = cmdgen.CommandGenerator().nextCmd(
        cmdgen.CommunityData('public', mpModel=0), cmdgen.UdpTransportTarget(
          (host, 161), timeout=self.timeout, retries=0), desc_oid, pdls_oid)
      
      # exit on error
      if error: raise Exception(error)
      if error_status: raise Exception(error_status.prettyPrint())
      
      # parse response
      for row in binds:
        for key, val in row:
          if desc_oid in str(key): desc.append(str(val))
          if pdls_oid in str(key): pdls.append(str(val))
      
      # get name of device
      model = item(desc)
      
      # get language support
      langs = ','.join(pdls)
      
      languageCheck = filter(None, [re.findall(re.escape(pdl), langs, re.I) for pdl in lang])
      if len(languageCheck) > 0:
        self.support += languageCheck
      
      if self.set_support(model):
        output().green_("found [%s]" % (model))
      else:
        output().errmsg_("not found", "check successful but no data")
      
    except NameError:
      output().errmsg_("not found", "pysnmp module not installed")
      
    except Exception as e:
      output().errmsg_("not found", e)
      
  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # feedback on language support
  def feedback(self, support, lang):
    sys.stdout.write("Checking for %-21s" % (lang + " support: "))
    if support: output().green_("found")
    else: output().warning_("not found")

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # set language support
  def set_support(self, model):
    ### model_stripped = re.sub(r'(\d|\s|-)[a-zA-Z]+$', '', model)
    '''
    ┌───────────────────────────────────────────────────────┐
    │ Experimental -- This might introduce false positives! │
    ├───────────────────────────────────────────────────────┤
    │ The stripped down version of the model string removes │
    │ endings like '-series', ' printer' (maybe localized), │
    │ 'd' (duplex), 't' (tray), 'c' (color), 'n' (network). │
    └───────────────────────────────────────────────────────┘
    '''
    if model and model != "":
        returnValues = printerModelDatabase().get_matching_models(self.mode, model)
        if len(returnValues) > 0:
            self.support += returnValues
            #print(self.support)
            return True
    return False

  #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  # open database of supported devices
  def get_models(self, file):
    try:
      with open(self.rundir + "db" + os.path.sep + file, 'r') as f:
        models = filter(None, (line.strip() for line in f))
      f.close()
      return models
    except IOError as e:
      output().errmsg_("Cannot open file", e)
      return []
