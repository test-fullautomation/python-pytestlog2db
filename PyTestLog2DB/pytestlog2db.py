#  Copyright 2020-2026 Robert Bosch GmbH
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# *******************************************************************************
#
# File: pytestlog2db.py
#
# Initialy created by Tran Duy Ngoan(RBVH/ECM11) / November 2022
#lxml
# This tool is used to parse the pytest JUnit XML report file(s)
# then import them into TestResultWebApp's database
#
# History:
#
# 2022-11-22:
#  - initial version
#
# *******************************************************************************

import re
import uuid
import base64
import argparse
import os
import sys
import colorama as col
import json
from lxml import etree
from datetime import datetime, timedelta
from dateutil import parser
import platform

# Use importlib.metadata (Python 3.8+) with fallback to pkg_resources
try:
   from importlib.metadata import version as get_package_version
except ImportError:
   from pkg_resources import get_distribution
   def get_package_version(name):
      return get_distribution(name).version

from TestResultDBAccess import DBAccessFactory
from PyTestLog2DB.version import VERSION, VERSION_DATE

DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def __current_user():
   """
Get current executing user.\
This information is used as default value for `tester` when importing.

**Arguments:**

(*no arguments*)

**Returns:**

*  ``sUserName``

   / *Type*: str /

   User name of current user.
   """

   sUserName=""
   # allow windows system access only in windows systems
   if platform.system().lower()!="windows":
      try:
         sUserName=os.getenv("USER","")
      except Exception as reason:
         pass
   else:
      import ctypes
      try:
         GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
         NameDisplay = 3

         size = ctypes.pointer(ctypes.c_ulong(0))
         GetUserNameEx(NameDisplay, None, size)

         nameBuffer = ctypes.create_unicode_buffer(size.contents.value)
         GetUserNameEx(NameDisplay, nameBuffer, size)

         sUserName=nameBuffer.value
      except:
         pass

   return sUserName

def __curent_testtool():
   """
Get current versions of Python and PyTest.\
This information is used as default value for `testtool` when importing.

**Arguments:**

(*no arguments*)

**Returns:**

   / *Type*: str /

   Current PyTest and Python verions as testtool.\
   E.g: PyTest 6.2.5 (Python 3.9.0)
   """
   sPytestVersion = "unknown_version"
   # Try to get pytest version
   # Incase pytest is not installed, set to 'unknown_version'
   try:
      sPytestVersion = get_package_version('pytest')
   except:
      pass

   return f"PyTest {sPytestVersion} (Python {platform.python_version()})"

CONFIG_SCHEMA = {
   "components" : [str, dict],
   "variant"   : str,
   "version_sw": str,
   "version_hw": str,
   "version_test": str,
   "testtool"  :  str,
   "tester"    :  str
}

DEFAULT_METADATA = {
   "components"   :  "unknown",
   "variant"      :  "PyTest",
   "version_sw"   :  "",
   "version_hw"   :  "",
   "version_test" :  "",
   "testtool"     :  __curent_testtool(),
   "tester"       :  __current_user()
}

iTotalTestcase = 0
iSuccessTestcase = 0
dComponentCounter = {}

class Logger():
   """
Logger class for logging message.
   """
   output_logfile = None
   output_console = True
   color_normal   = col.Fore.WHITE + col.Style.NORMAL
   color_error    = col.Fore.RED + col.Style.BRIGHT
   color_warn     = col.Fore.YELLOW + col.Style.BRIGHT
   color_reset    = col.Style.RESET_ALL + col.Fore.RESET + col.Back.RESET
   prefix_warn    = "WARN: "
   prefix_error   = "ERROR: "
   prefix_fatalerror = "FATAL ERROR: "
   prefix_all = ""
   dryrun = False

   @classmethod
   def config(cls, output_console=True, output_logfile=None, indent=0, dryrun=False):
      """
Configure Logger class.

**Arguments:**

*  ``output_console``

   / *Condition*: optional / *Type*: bool / *Default*: True /

   Write message to console output.

*  ``output_logfile``

   / *Condition*: optional / *Type*: str / *Default*: None /

   Path to log file output.

*  ``indent``

   / *Condition*: optional / *Type*: int / *Default*: 0 /

   Offset indent.

*  ``dryrun``

   / *Condition*: optional / *Type*: bool / *Default*: True /

   If set, a prefix as 'dryrun' is added for all messages.

**Returns:**

(*no returns*)
      """
      cls.output_console = output_console
      cls.output_logfile = output_logfile
      cls.dryrun = dryrun
      if cls.dryrun:
         cls.prefix_all = cls.color_warn + "DRYRUN  " + cls.color_reset

   @classmethod
   def log(cls, msg="", color=None, indent=0):
      """
Write log message to console/file output.

**Arguments:**

*  ``msg``

   / *Condition*: optional / *Type*: str / *Default*: "" /

   Message which is written to output.

*  ``color``

   / *Condition*: optional / *Type*: str / *Default*: None /

   Color style for the message.

*  ``indent``

   / *Condition*: optional / *Type*: int / *Default*: 0 /

   Offset indent.

**Returns:**

(*no returns*)
      """
      if color==None:
         color = cls.color_normal
      if cls.output_console:
         print(cls.prefix_all + cls.color_reset + color + " "*indent + msg + cls.color_reset)
      if cls.output_logfile!=None and os.path.isfile(cls.output_logfile):
         with open(cls.output_logfile, "a") as f:
            f.write(" "*indent + msg)
      return

   @classmethod
   def log_warning(cls, msg):
      """
Write warning message to console/file output.

**Arguments:**

*  ``msg``

   / *Condition*: required / *Type*: str /

   Warning message which is written to output.

**Returns:**

(*no returns*)
      """
      cls.log(cls.prefix_warn+str(msg), cls.color_warn)

   @classmethod
   def log_error(cls, msg, fatal_error=False):
      """
Write error message to console/file output.

**Arguments:**

*  ``msg``

   / *Condition*: required / *Type*: str /

   Error message which is written to output.

*  ``fatal_error``

   / *Condition*: optional / *Type*: bool / *Default*: False /

   If set, tool will terminate after logging error message.

**Returns:**

(*no returns*)
      """
      prefix = cls.prefix_error
      if fatal_error:
         prefix = cls.prefix_fatalerror

      cls.log(prefix+str(msg), cls.color_error)
      if fatal_error:
         cls.log(f"{(sys.argv[0])} has been stopped!", cls.color_error)
         exit(1)

def __process_commandline():
   """
Process provided argument(s) from command line.

Avalable arguments in command line:

   - `-v`, `--version` : tool version information.
   - `resultxmlfile` : path to the xml pytest result file or directory of result files to be imported.
   - `server` : server which hosts the database (IP or URL).
   - `user` : user for database login.
   - `password` : password for database login.
   - `database` : database name.
   - `--recursive` : if True, then the path is searched recursively for *.xml files to be imported.
   - `--dryrun` : if True, then verify all input arguments (includes DB connection) and show what would be done.
   - `--append` : if True, then allow to append new result(s) to existing execution result UUID which is provided by --UUID argument.
   - `--UUID` : UUID used to identify the import and version ID on TestResultWebApp.
   - `--variant` : variant name to be set for this import.
   - `--versions` : metadata: Versions (Software;Hardware;Test) to be set for this import.
   - `--config` : configuration json file for component mapping information.
   - `--interface` : database access interface.
   - `--testrunurl`: link to test execution job: Jenkins job, Gitlab CI/CD pipeline, ...

**Arguments:**

(*no arguments*)

**Returns:**

   / *Type*: `ArgumentParser` object /

   ArgumentParser object.
   """
   cmdlineparser=argparse.ArgumentParser(prog="PyTestLog2DB (PyTestXMLReport to TestResultWebApp importer)",
                                         description="PyTestLog2DB imports pytest JUnit XML report file(s)" + \
                                                     "generated by pytest into a WebApp database."
                                        )

   cmdlineparser.add_argument('-v', '--version',action='version', version=f'v{VERSION} ({VERSION_DATE})',help='version of the PyTestLog2DB importer.')
   cmdlineparser.add_argument('resultxmlfile', type=str, help='absolute or relative path to the pytest JUnit XML report file or directory of report files to be imported.')
   cmdlineparser.add_argument('server', type=str, help='server which hosts the database (IP or URL).')
   cmdlineparser.add_argument('user', type=str, help='user for database login.')
   cmdlineparser.add_argument('password', type=str, help='password for database login.')
   cmdlineparser.add_argument('database', type=str, help='database schema for database login.')
   cmdlineparser.add_argument('--recursive', action="store_true", help='if set, then the path is searched recursively for output files to be imported.')
   cmdlineparser.add_argument('--dryrun', action="store_true", help='if set, then verify all input arguments (includes DB connection) and show what would be done.')
   cmdlineparser.add_argument('--append', action="store_true", help='is used in combination with --UUID <UUID>.' +\
                              ' If set, allow to append new result(s) to existing execution result UUID in --UUID argument.')
   cmdlineparser.add_argument('--UUID', type=str, help='UUID used to identify the import and version ID on webapp.' + \
                              ' If not provided PyTestLog2DB will generate an UUID for the whole import.')
   cmdlineparser.add_argument('--variant', type=str, help='variant name to be set for this import.')
   cmdlineparser.add_argument('--versions', type=str, help='metadata: Versions (Software;Hardware;Test) to be set for this import (semicolon separated).')
   cmdlineparser.add_argument('--config', type=str, help='configuration json file for component mapping information.')
   cmdlineparser.add_argument('--interface', choices=['db', 'rest'], default='db', help='database access interface.')
   cmdlineparser.add_argument('--testrunurl', type=str, default="", help='link to test execution job: Jenkins job, Gitlab CI/CD pipeline, ...')

   return cmdlineparser.parse_args()

def collect_xml_result_files(path, search_recursive=False):
   """
Collect all valid Robot xml result file in given path.

**Arguments:**

*  ``path``

   / *Condition*: required / *Type*: str /

   Path to Robot result folder or file to be searched.

*  ``search_recursive``

   / *Condition*: optional / *Type*: bool / *Default*: False /

   If set, the given path is searched recursively for xml result files.

**Returns:**

*  ``lFoundFiles``

   / *Type*: list /

   List of valid xml result file(s) in given path.
   """
   lFoundFiles = []
   if os.path.exists(path):
      if os.path.isfile(path):
         validate_xml_result(path)
         lFoundFiles.append(path)
      else:
         if search_recursive:
            Logger.log("Searching *.xml result files recursively...")
            for root, _, files in os.walk(path):
               for file in files:
                  if file.endswith(".xml"):
                     xml_result_pathfile = os.path.join(root, file)
                     Logger.log(xml_result_pathfile, indent=2)
                     validate_xml_result(xml_result_pathfile)
                     lFoundFiles.append(xml_result_pathfile)
         else:
            Logger.log("Searching *.xml result files...")
            for file in os.listdir(path):
               if file.endswith(".xml"):
                  xml_result_pathfile = os.path.join(path, file)
                  Logger.log(xml_result_pathfile, indent=2)
                  validate_xml_result(xml_result_pathfile)
                  lFoundFiles.append(xml_result_pathfile)

         # Terminate tool with error when no logfile under provided folder
         if len(lFoundFiles) == 0:
            Logger.log_error(f"No *.xml result file under '{path}' folder.", fatal_error=True)
   else:
      Logger.log_error(f"Given resultxmlfile is not existing: '{path}'", fatal_error=True)

   return lFoundFiles

def validate_xml_result(xml_result, xsd_schema=os.path.join(os.path.dirname(__file__),'xsd/junit.xsd'), exit_on_failure=True):
   """
Verify the given xml result file is valid or not.

**Arguments:**

*  ``xml_result``

   / *Condition*: required / *Type*: str /

   Path to PyTest result file.

*  ``xsd_schema``

   / *Condition*: optional / *Type*: str / *Default*: <installed_folder>\/xsd\/junit.xsd /

   Path to Robot schema *.xsd file.

*  ``exit_on_failure``

   / *Condition*: optional / *Type*: bool / *Default*: True /

   If set, exit with fatal error if the schema validation of given xml file failed.

**Returns:**

*  / *Type*: bool /

   True if the given xml result is valid with the provided schema *.xsd.
   """
   try:
      xmlschema_doc = etree.parse(xsd_schema)
      xmlschema = etree.XMLSchema(xmlschema_doc)
   except Exception as reason:
      Logger.log_error(f"schema xsd file '{xsd_schema}' is not a valid.\nReason: {reason}", fatal_error=True)

   if exit_on_failure:
      try:
         xml_doc = etree.parse(xml_result)
         xmlschema.assert_(xml_doc)
      except AssertionError as reason:
         Logger.log_error(f"xml result file '{xml_result}' is not a valid PyTest result.\nReason: {reason}", fatal_error=True)
      except Exception as reason:
         Logger.log_error(f"result file '{xml_result}' is not a valid xml format.\nReason: {reason}", fatal_error=True)

   return xmlschema.validate(xml_doc)

def is_valid_uuid(uuid_to_test, version=4):
   """
Verify the given UUID is valid or not.

**Arguments:**

*  ``uuid_to_test``

   / *Condition*: required / *Type*: str /

   UUID to be verified.

*  ``version``

   / *Condition*: optional / *Type*: int / *Default*: 4 /

   UUID version.

**Returns:**

*  ``bValid``

   / *Type*: bool /

   True if the given UUID is valid.
   """
   bValid = False
   try:
      uuid_obj = uuid.UUID(uuid_to_test, version=version)
   except:
      return bValid

   if str(uuid_obj) == uuid_to_test:
      bValid = True

   return bValid

def is_valid_config(dConfig, dSchema=CONFIG_SCHEMA, bExitOnFail=True):
   """
Validate the json configuration base on given schema.

Default schema supports below information:

.. code:: python

   CONFIG_SCHEMA = {
      "components": [str, dict],
      "variant"   : str,
      "version_sw": str,
      "version_hw": str,
      "version_test": str,
      "testtool"  :  str,
      "tester"    :  str
   }

**Arguments:**

*  ``dConfig``

   / *Condition*: required / *Type*: dict /

   Json configuration object to be verified.

*  ``dSchema``

   / *Condition*: optional / *Type*: dict / *Default*: CONFIG_SCHEMA /

   Schema for the validation.

*  ``bExitOnFail``

   / *Condition*: optional / *Type*: bool / *Default*: True /

   If True, exit tool in case the validation is fail.

**Returns:**

*  ``bValid``

   / *Type*: bool /

   True if the given json configuration data is valid.
   """
   bValid = True
   for key in dConfig:
      if key in dSchema.keys():
         # List of support types
         if isinstance(dSchema[key], list):
            if type(dConfig[key]) not in dSchema[key]:
               bValid = False
         # Fixed type
         else:
            if type(dConfig[key]) != dSchema[key]:
               bValid = False

         if not bValid:
            Logger.log_error(f"Value of '{key}' has wrong type '{type(dConfig[key])}' in configuration json file.", fatal_error=bExitOnFail)
            break

      else:
         bValid = False
         Logger.log_error(f"Invalid key '{key}' in configuration json file.", fatal_error=bExitOnFail)
         break

   return bValid


def parse_pytest_xml(*xmlfiles):
   """
Parse and merge all given pytest *.xml result files into one result file.\
Besides, `starttime` and `endtime` are also calculated and added in the merged result.

**Arguments:**

*  ``xmlfiles``

   / *Condition*: required / *Type*: str /

   Path to pytest *.xml result file(s).

**Returns:**

*  ``oMergedTree``

   / *Type*: `etree._Element` object /

   The result object which is parsed from provided pytest *.xml result file(s).
   """
   oMergedTree = None
   dtStartTime = None
   dtEndTime   = None

   try:
      for item in xmlfiles:
         oTree = etree.parse(item).getroot()
         if oMergedTree == None:
            oMergedTree = oTree
            sStartTime  = oMergedTree.getchildren()[0].get("timestamp")
            dtStartTime = parser.parse(sStartTime)
            dtEndTime   = dtStartTime + timedelta(seconds=float(oMergedTree.getchildren()[0].get("time")))
         else:
            oAdditionalTree = etree.parse(item)
            for oSuite in oAdditionalTree.getroot().iterchildren("testsuite"):
               oMergedTree.append(oSuite)
               dtTimestamp = parser.parse(oSuite.get("timestamp"))

               # check starttime and endtime for the execution result
               if dtTimestamp < dtStartTime:
                  dtStartTime = dtTimestamp
               elif (dtTimestamp + timedelta(seconds=float(oSuite.get("time"))))> dtEndTime:
                  dtEndTime = dtTimestamp

   except Exception as reason:
      Logger.log_error(f"Error when merging pytest xml files. Reason: {reason}", fatal_error=True)

   # Additional attributes for testsuites
   oMergedTree.attrib["starttime"] = datetime.strftime(dtStartTime, DB_DATETIME_FORMAT)
   oMergedTree.attrib["endtime"] = datetime.strftime(dtEndTime, DB_DATETIME_FORMAT)

   return oMergedTree

def get_branch_from_swversion(sw_version):
   """
Get branch name from software version information.

Convention of branch information in suffix of software version:

*  All software version with .0F is the main/freature branch.
   The leading number is the current year. E.g. ``17.0F03``
*  All software version with ``.1S``, ``.2S``, ... is a stabi branch.
   The leading number is the year of branching out for stabilization.
   The number before "S" is the order of branching out in the year.

**Arguments:**

*  ``sw_version``

   / *Condition*: required / *Type*: str /

   Software version.

**Returns:**

*  ``branch_name``

   / *Type*: str /

   Branch name.
   """
   branch_name = "main"
   version_number=re.findall(r"(\d+\.)(\d+)([S,F])\d+",sw_version.upper())
   try:
      branch_name = "".join(version_number[0])
   except:
      pass
   if branch_name.endswith(".0F"):
      branch_name="main"
   return branch_name

def get_test_result(oTest):
   """
Get test result from provided Testcase object.

**Arguments:**

*  ``oTest``

   / *Condition*: required / *Type*: `etree._Element` object /

   Testcase object.

**Returns:**

   / *Type*: typle /

   Testcase result which contains `result_main`, `lastlog` and `result_return`.
   """
   main_result = "Passed"
   traceback_log = ""
   return_code = 11
   if failure := list(oTest.iterchildren("failure")):
      main_result = "Failed"
      traceback_log = f"{failure[0].get('message')}\n{failure[0].text}"
      return_code = 12
   elif error := list(oTest.iterchildren("error")):
      main_result = "unknown"
      traceback_log = f"{error[0].get('message')}\n{error[0].text}"
      return_code = 5
   elif list(oTest.iterchildren("skipped")):
      main_result = "unknown"
      traceback_log = f"This test is skipped."
      return_code = 20

   return (main_result, str(base64.b64encode(traceback_log.encode()), encoding='utf-8'), return_code)

def process_component_info(dConfig, sTestClassname):
   """
Return the component name bases on provided testcase's classname and component
mapping.

**Arguments:**

*  ``dConfig``

   / *Condition*: required / *Type*: dict /

   Configuration which contains the mapping between component and testcase's classname.

*  ``sTestClassname``

   / *Condition*: required / *Type*: str /

   Testcase's classname to get the component info.

**Returns:**

*  ``sComponent``

   / *Type*: typle /

   Component name maps with given testcase's classname.
   Otherwise, "unknown" will be return as component name.
   """
   sComponent = "unknown"

   if dConfig != None and "components" in dConfig:
      # component info as object in json file
      if isinstance(dConfig["components"], dict):
         for cmpt in dConfig["components"]:
            # component name maps with an array of classnames
            if isinstance(dConfig["components"][cmpt], list):
               bFound = False
               for clsName in dConfig["components"][cmpt]:
                  if clsName in sTestClassname:
                     sComponent = cmpt
                     bFound = True
                     break
               if bFound:
                  break
            # component maps with single classname
            elif isinstance(dConfig["components"][cmpt], str):
               if dConfig["components"][cmpt] in sTestClassname:
                  sComponent = cmpt
                  break
      # component info as string in json file
      elif isinstance(dConfig["components"], str) and dConfig["components"].strip() != "":
         sComponent = dConfig["components"]

   return sComponent

def process_config_file(config_file):
   """
Parse information from configuration file:

*  ``component``:

   .. code:: python

      {
         "components" : {
            "componentA" : "componentA/path/to/testcase",
            "componentB" : "componentB/path/to/testcase",
            "componentC" : [
               "componentC1/path/to/testcase",
               "componentC2/path/to/testcase"
            ]
         }
      }

   Then all testcases which their paths contain ``componentA/path/to/testcase``
   will be belong to ``componentA``, ...

**Arguments:**

*  ``config_file``

   / *Condition*: required / *Type*: str /

   Path to configuration file.

**Returns:**

*  ``dConfig``

   / *Type*: dict /

   Configuration object.
   """

   with open(config_file, encoding='utf-8') as f:
      try:
         dConfig = json.load(f)
      except Exception as reason:
         Logger.log_error(f"Cannot parse the json file '{config_file}'. Reason: {reason}", fatal_error=True)

   if not is_valid_config(dConfig, bExitOnFail=False):
      Logger.log_error(f"Error in configuration file '{config_file}'.", fatal_error=True)

   return dConfig

def process_test(db, test, file_id, test_result_id, component_name, test_number, start_time):
   """
Process test case data and create new test case record.

**Arguments:**

*  ``db``

   / *Condition*: required / *Type*: `CDataBase` object /

   CDataBase object.

*  ``test``

   / *Condition*: required / *Type*: `etree._Element` object /

   Robot test object.

*  ``file_id``

   / *Condition*: required / *Type*: int /

   File ID for mapping.

*  ``test_result_id``

   / *Condition*: required / *Type*: str /

   Test result ID for mapping.

*  ``component_name``

   / *Condition*: required / *Type*: str /

   Component name which this test case is belong to.

*  ``test_number``

   / *Condition*: required / *Type*: int /

   Order of test case in file.

*  ``start_time``

   / *Condition*: required / *Type*: `datetime` object /

   Start time of testcase.

**Returns:**

   / *Type*: float /

   Duration (in second) of test execution.
   """
   global iTotalTestcase
   global iSuccessTestcase
   global dComponentCounter
   iTotalTestcase += 1
   _tbl_case_name  = test.get("name")
   _tbl_case_issue = ""
   _tbl_case_tcid  = ""
   _tbl_case_fid   = ""
   _tbl_case_testnumber  = test_number
   _tbl_case_repeatcount = 1
   _tbl_case_component   = component_name
   _tbl_case_time_start  = datetime.strftime(start_time, DB_DATETIME_FORMAT)
   if _tbl_case_component not in dComponentCounter:
      dComponentCounter[_tbl_case_component] = 0

   try:
      _tbl_case_result_main, _tbl_case_lastlog, _tbl_case_result_return = get_test_result(test)
   except Exception as reason:
      Logger.log_error(f"Error when getting PyTest result of test '{_tbl_case_name}'. Reason: {reason}", fatal_error=True)
      return

   _tbl_case_result_state   = "complete"
   _tbl_case_result_return  = 11
   _tbl_case_counter_resets = 0
   _tbl_test_result_id = test_result_id
   _tbl_file_id = file_id

   if not Logger.dryrun:
      try:
         tbl_case_id = db.nCreateNewSingleTestCase(_tbl_case_name,
                                                   _tbl_case_issue,
                                                   _tbl_case_tcid,
                                                   _tbl_case_fid,
                                                   _tbl_case_testnumber,
                                                   _tbl_case_repeatcount,
                                                   _tbl_case_component,
                                                   _tbl_case_time_start,
                                                   _tbl_case_result_main,
                                                   _tbl_case_result_state,
                                                   _tbl_case_result_return,
                                                   _tbl_case_counter_resets,
                                                   _tbl_case_lastlog,
                                                   _tbl_test_result_id,
                                                   _tbl_file_id
                                                )
      except Exception as reason:
         Logger.log_error(f"Cannot create new test case result for test '{_tbl_case_name}' in database.\nReason: {reason}")
         return float(test.get("time"))
   else:
      tbl_case_id = "testcase id for dryrun"
   iSuccessTestcase += 1
   dComponentCounter[_tbl_case_component] += 1
   component_msg = f" (component: {_tbl_case_component})" if _tbl_case_component != "unknown" else ""
   Logger.log(f"Created test case result for test '{_tbl_case_name}' successfully: {str(tbl_case_id)}{component_msg}", indent=4)

   return float(test.get("time"))

def process_suite(db, suite, _tbl_test_result_id, dConfig=None):
   """
Process to the lowest suite level (test file):

* Create new file and its header information
* Then, process all child test cases

**Arguments:**

*  ``db``

   / *Condition*: required / *Type*: `CDataBase` object /

   CDataBase object.

*  ``suite``

   / *Condition*: required / *Type*: `etree._Element` object /

   Robot suite object.

*  ``_tbl_test_result_id``

   / *Condition*: required / *Type*: str /

   UUID of test result for importing.

*  ``dConfig``

   / *Condition*: required / *Type*: dict / *Default*: None /

   Configuration data which is parsed from given json configuration file.

**Returns:**

(*no returns*)
   """

   # File metadata
   previous_file_name = None
   suite_name = suite.get("name")
   _tbl_file_id = None
   _tbl_file_tester_account = dConfig["tester"]
   _tbl_file_tester_machine = suite.get("hostname")
   test_start_time      = parser.parse(suite.get("timestamp"))
   _tbl_file_time_start = datetime.strftime(test_start_time, DB_DATETIME_FORMAT)
   _tbl_file_time_end   = datetime.strftime(test_start_time + timedelta(seconds=float(suite.get("time"))), DB_DATETIME_FORMAT)

   test_number = 1
   for test in suite.iterchildren("testcase"):
      _tbl_file_name = test.get("classname") or suite_name
      component_name = process_component_info(dConfig, _tbl_file_name)
      # Create new testfile if not existing in this execution (different classname with previous one)
      if previous_file_name != _tbl_file_name:
         _tbl_header_testtoolconfiguration_testtoolname      = ""
         _tbl_header_testtoolconfiguration_testtoolversion   = ""
         _tbl_header_testtoolconfiguration_pythonversion     = ""
         if dConfig["testtool"]:
            sFindstring = r"([a-zA-Z\s\_]+[^\s])\s+([\d\.rcab]+)\s+\(Python\s+(.*)\)"
            oTesttool = re.search(sFindstring, dConfig["testtool"])
            if oTesttool:
               _tbl_header_testtoolconfiguration_testtoolname    = oTesttool.group(1)
               _tbl_header_testtoolconfiguration_testtoolversion = oTesttool.group(2)
               _tbl_header_testtoolconfiguration_pythonversion   = oTesttool.group(3)

         _tbl_header_testtoolconfiguration_projectname     = dConfig["variant"]
         _tbl_header_testtoolconfiguration_logfileencoding = "UTF-8"
         _tbl_header_testtoolconfiguration_testfile        = _tbl_file_name
         _tbl_header_testtoolconfiguration_logfilepath     = ""
         _tbl_header_testtoolconfiguration_logfilemode     = ""
         _tbl_header_testtoolconfiguration_ctrlfilepath    = ""
         _tbl_header_testtoolconfiguration_configfile      = ""
         _tbl_header_testtoolconfiguration_confname        = ""

         _tbl_header_testfileheader_author           = dConfig["tester"]
         _tbl_header_testfileheader_project          = dConfig["variant"]
         _tbl_header_testfileheader_testfiledate     = ""
         _tbl_header_testfileheader_version_major    = ""
         _tbl_header_testfileheader_version_minor    = ""
         _tbl_header_testfileheader_version_patch    = ""
         _tbl_header_testfileheader_keyword          = ""
         _tbl_header_testfileheader_shortdescription = ""
         _tbl_header_testexecution_useraccount       = dConfig["tester"]
         _tbl_header_testexecution_computername      = _tbl_file_tester_machine

         _tbl_header_testrequirements_documentmanagement = ""
         _tbl_header_testrequirements_testenvironment    = ""

         _tbl_header_testbenchconfig_name    = ""
         _tbl_header_testbenchconfig_data    = ""
         _tbl_header_preprocessor_filter     = ""
         _tbl_header_preprocessor_parameters = ""

         if not Logger.dryrun:
            try:
               _tbl_file_id = db.nCreateNewFile(_tbl_file_name,
                                                _tbl_file_tester_account,
                                                _tbl_file_tester_machine,
                                                _tbl_file_time_start,
                                                _tbl_file_time_end,
                                                _tbl_test_result_id)
               db.vCreateNewHeader(_tbl_file_id,
                                 _tbl_header_testtoolconfiguration_testtoolname,
                                 _tbl_header_testtoolconfiguration_testtoolversion,
                                 _tbl_header_testtoolconfiguration_projectname,
                                 _tbl_header_testtoolconfiguration_logfileencoding,
                                 _tbl_header_testtoolconfiguration_pythonversion,
                                 _tbl_header_testtoolconfiguration_testfile,
                                 _tbl_header_testtoolconfiguration_logfilepath,
                                 _tbl_header_testtoolconfiguration_logfilemode,
                                 _tbl_header_testtoolconfiguration_ctrlfilepath,
                                 _tbl_header_testtoolconfiguration_configfile,
                                 _tbl_header_testtoolconfiguration_confname,

                                 _tbl_header_testfileheader_author,
                                 _tbl_header_testfileheader_project,
                                 _tbl_header_testfileheader_testfiledate,
                                 _tbl_header_testfileheader_version_major,
                                 _tbl_header_testfileheader_version_minor,
                                 _tbl_header_testfileheader_version_patch,
                                 _tbl_header_testfileheader_keyword,
                                 _tbl_header_testfileheader_shortdescription,
                                 _tbl_header_testexecution_useraccount,
                                 _tbl_header_testexecution_computername,

                                 _tbl_header_testrequirements_documentmanagement,
                                 _tbl_header_testrequirements_testenvironment,

                                 _tbl_header_testbenchconfig_name,
                                 _tbl_header_testbenchconfig_data,
                                 _tbl_header_preprocessor_filter,
                                 _tbl_header_preprocessor_parameters
                                 )
            except Exception as reason:
               Logger.log_error(f"Cannot create new test file result for file '{_tbl_file_name}' in database.\nReason: {reason}",
                                  fatal_error=True)
         else:
            _tbl_file_id = "file id for dryrun"
         Logger.log(f"Created test file result for classname '{_tbl_file_name}' successfully: {str(_tbl_file_id)}", indent=2)
         previous_file_name = _tbl_file_name

      # Process testcase
      if _tbl_file_id:
         duration = process_test(db, test, _tbl_file_id, _tbl_test_result_id, component_name, test_number, test_start_time)
         test_start_time += timedelta(seconds=duration)
         test_number += 1
      else:
         Logger.log_error(f"No found testfile ID for classname {_tbl_file_name}.", fatal_error=True)

def PyTestLog2DB(args=None):
   """
Import pytest results from ``*.xml`` file(s) to TestResultWebApp's database.

Flow to import PyTest results to database:

1. Process provided arguments from command line.
2. Parse PyTest results.
3. Connect to database.
4. Import results into database.
5. Disconnect from database.

**Arguments:**

*  ``args``

   / *Condition*: required / *Type*: `ArgumentParser` object /

   Argument parser object which contains:

   * `resultxmlfile` : path to the xml result file or directory of result files to be imported.
   * `server` : server which hosts the database (IP or URL).
   * `user` : user for database login.
   * `password` : password for database login.
   * `database` : database name.
   * `recursive` : if True, then the path is searched recursively for log files to be imported.
   * `dryrun` : if True, then verify all input arguments (includes DB connection) and show what would be done.
   * `append` : if True, then allow to append new result(s) to existing execution result UUID which is provided by --UUID argument.
   * `UUID` : UUID used to identify the import and version ID on TestResultWebApp.
   * `variant` : variant name to be set for this import.
   * `versions` : metadata: Versions (Software;Hardware;Test) to be set for this import.
   * `config` : configuration json file for component mapping information.
   * `testrunurl`: link to test execution job: Jenkins job, Gitlab CI/CD pipeline, ...

**Returns:**

(*no returns*)
   """
   # 1. process provided arguments from command line as default
   args = __process_commandline()
   Logger.config(dryrun=args.dryrun)

   # 2. Parse results from PyTest xml result file(s)
   listEntries = collect_xml_result_files(args.resultxmlfile, args.recursive)

   pytest_result = parse_pytest_xml(*listEntries)

   # Validate provided UUID
   if args.UUID!=None:
      if is_valid_uuid(args.UUID):
         pass
      else:
         Logger.log_error(f"The uuid provided is not valid: '{args.UUID}'", fatal_error=True)

   # Validate provided versions info (software;hardware;test)
   arVersions = []
   if args.versions!=None and args.versions.strip() != "":
      arVersions=args.versions.split(";")
      arVersions=[x.strip() for x in arVersions]
      if len(arVersions)>3:
         Logger.log_error(f"The provided versions information is not valid: '{str(args.versions)}'",
                          fatal_error=True)

   # Validate provided configuration file (component, variant, version_sw)
   dConfig = {}
   if args.config != None:
      if os.path.isfile(args.config):
         dConfig = process_config_file(args.config)
      else:
         Logger.log_error(f"The provided config file is not existing: '{args.config}'", fatal_error=True)

   # Set default value for missing metadata bases on DEFAULT_METADATA
   for key in DEFAULT_METADATA:
      if key not in dConfig:
         dConfig[key] = DEFAULT_METADATA[key]


   # 3. Connect to database
   db = DBAccessFactory().create(args.interface)
   try:
      db.connect(args.server,
                 args.user,
                 args.password,
                 args.database,
                 "utf8mb4")
   except Exception as reason:
      Logger.log_error(f"Could not connect to database: '{reason}'", fatal_error=True)

   # 4. Import results into database
   #    Create new execution result in database
   #    |
   #    '---Create new file result(s)
   #        |
   #        '---Create new test result(s)
   try:
      bUseDefaultPrjVariant = True
      bUseDefaultVersionSW  = True
      sMsgVarirantSetBy = sMsgVersionSWSetBy = "default value"

      # Process project/variant
      sVariant = dConfig["variant"]
      if args.variant!=None and args.variant.strip() != "":
         bUseDefaultPrjVariant = False
         sMsgVarirantSetBy = "from --variant commandline argument"
         sVariant = args.variant.strip()
      elif sVariant != DEFAULT_METADATA["variant"]:
         bUseDefaultPrjVariant = False
         sMsgVarirantSetBy = f"from configuration '{args.config}' file provided by --config"
      _tbl_prj_project = _tbl_prj_variant = sVariant

      # Process versions info
      sVersionSW = dConfig["version_sw"]
      sVersionHW = dConfig["version_hw"]
      sVersionTest = dConfig["version_test"]
      if sVersionSW != DEFAULT_METADATA["version_sw"]:
         bUseDefaultVersionSW = False
         sMsgVersionSWSetBy = f"from configuration '{args.config}' file provided by --config"
      if len(arVersions) > 0:
         bUseDefaultVersionSW = False
         sMsgVersionSWSetBy = "from --versions commandline argument"
         if len(arVersions)==1 or len(arVersions)==2 or len(arVersions)==3:
            sVersionSW = arVersions[0]
         if len(arVersions)==2 or len(arVersions)==3:
            sVersionHW = arVersions[1]
         if len(arVersions)==3:
            sVersionTest = arVersions[2]
      _tbl_result_version_sw_target = sVersionSW
      _tbl_result_version_hardware  = sVersionHW
      _tbl_result_version_sw_test   = sVersionTest

      # Set version as start time of the execution if not provided in metadata
      # Format: %Y%m%d_%H%M%S from %Y-%m-%d %H:%M:%S
      if _tbl_result_version_sw_target=="":
         _tbl_result_version_sw_target = datetime.strftime(parser.parse(pytest_result.get("starttime")), "%Y%m%d_%H%M%S")

      if not args.append:
         Logger.log(f"Set project/variant to '{sVariant}' ({sMsgVarirantSetBy})")
         Logger.log(f"Set version_sw to '{_tbl_result_version_sw_target}' ({sMsgVersionSWSetBy})")

      # Process branch info from software version
      _tbl_prj_branch = get_branch_from_swversion(_tbl_result_version_sw_target)

      # Process UUID info
      if args.UUID != None:
         _tbl_test_result_id = args.UUID
      else:
         _tbl_test_result_id = str(uuid.uuid4())
         if args.append:
            Logger.log_error("'--append' argument should be used in combination with '--UUID <UUID>` argument.", fatal_error=True)

      # Process start/end time info
      _tbl_result_time_start = pytest_result.get("starttime")
      _tbl_result_time_end   = pytest_result.get("endtime")

      # Process other info
      _tbl_result_interpretation = ""
      _tbl_result_jenkinsurl     = args.testrunurl
      _tbl_result_reporting_qualitygate = ""

      # Check the UUID is existing or not
      error_indent = len(Logger.prefix_fatalerror)*' '
      _db_result_info = db.arGetProjectVersionSWByID(_tbl_test_result_id)
      if _db_result_info:
         if args.append:
            # Check given variant/project and version_sw (not default values) with existing values in db
            _db_prj_variant = _db_result_info[0]
            _db_version_sw  = _db_result_info[1]
            if not bUseDefaultPrjVariant and _tbl_prj_variant != _db_prj_variant:
               Logger.log_error(f"Given project/variant '{_tbl_prj_variant}' ({sMsgVarirantSetBy}) is different with existing value '{_db_prj_variant}' in database.", fatal_error=True)
            elif not bUseDefaultVersionSW and _tbl_result_version_sw_target != _db_version_sw:
               Logger.log_error(f"Given version software '{_tbl_result_version_sw_target}' ({sMsgVersionSWSetBy}) is different with existing value '{_db_version_sw}' in database.", fatal_error=True)
            else:
               Logger.log(f"Append to existing test execution result for variant '{_db_prj_variant}' - version '{_db_version_sw}' - UUID '{_tbl_test_result_id}'.")
         else:
            Logger.log_error(f"Execution result with UUID '{_tbl_test_result_id}' is already existing. \
               \n{error_indent}Please use other UUID (or remove '--UUID' argument from your command) for new execution result. \
               \n{error_indent}Or add '--append' argument in your command to append new result(s) to this existing UUID.",
               fatal_error=True)
      else:
         if args.append:
            Logger.log_error(f"Execution result with UUID '{_tbl_test_result_id}' is not existing for appending.\
               \n{error_indent}Please use an existing UUID to append new result(s) to that UUID. \
               \n{error_indent}Or remove '--append' argument in your command to create new execution result with given UUID.",
               fatal_error=True)
         else:
            # Process new test result
            if not Logger.dryrun:
               db.sCreateNewTestResult(_tbl_prj_project,
                                       _tbl_prj_variant,
                                       _tbl_prj_branch,
                                       _tbl_test_result_id,
                                       _tbl_result_interpretation,
                                       _tbl_result_time_start,
                                       _tbl_result_time_end,
                                       _tbl_result_version_sw_target,
                                       _tbl_result_version_sw_test,
                                       _tbl_result_version_hardware,
                                       _tbl_result_jenkinsurl,
                                       _tbl_result_reporting_qualitygate)
            Logger.log(f"Created test execution result for variant '{_tbl_prj_variant}' - version '{_tbl_result_version_sw_target}' successfully: {str(_tbl_test_result_id)}")
   except Exception as reason:
      Logger.log_error(f"Could not create new execution result in database. Reason: {reason}", fatal_error=True)

   for suite in pytest_result.iterchildren("testsuite"):
      process_suite(db, suite, _tbl_test_result_id, dConfig)

   if not Logger.dryrun:
      db.vUpdateEvtbls()
      db.vFinishTestResult(_tbl_test_result_id)
      if args.append:
         db.vUpdateEvtbl(_tbl_test_result_id)

   # 5. Disconnect from database
   db.disconnect()
   import_mode_msg = "appended" if args.append else "written"
   testcnt_msg = f"All {iTotalTestcase}"
   extended_msg = ""
   if (iTotalTestcase>iSuccessTestcase):
      testcnt_msg  = f"{iSuccessTestcase} of {iTotalTestcase}"
      extended_msg = f" {iTotalTestcase-iSuccessTestcase} test cases are skipped because of errors."
   Logger.log()
   Logger.log(f"{testcnt_msg} test cases are {import_mode_msg} to database successfully.{extended_msg}")

   # Components's statistics
   iMaxlenCmptStr = len(max(dComponentCounter, key=len))
   for component in dComponentCounter:
      Logger.log(f"Component {component.ljust(iMaxlenCmptStr, ' ')} : {dComponentCounter[component]} test cases")

if __name__=="__main__":
   PyTestLog2DB()
