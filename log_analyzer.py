"""
Log Analyzer - This tool reads in a log file with each log entry organized as a well defined
header followed by a number of key-value pairs. My goals include:
1. Provide min, max, and avg latency between processing stages to find bottlenecks.
2. Provide summaries of groups, e.g. a summary of all log entries where a field has
a particular value.

Usage: To use this tool, you edit the log_analyzer.cfg to define the properties of the log
file you want to analyze, what analyses you want performed, the path to the log file
to analyze, and where to write its output. Then you run this tool with no command
line arguments.
"""

"""
author: Chris Lamke
"""

import logging
import time
import configparser
import os
import sys
import re
from datetime import datetime
from enum import Enum


from log_util import *
from fs_util import *
from excel_util import *


APP_NAME = "Log Analyzer"
APP_VERSION = "v0.1"
WELCOME_MSG = "Welcome to the Log Analyzer"
AUTHORS = "Chris Lamke"
SOURCE_LINK = "https://github.com/crlamke/log-analyzer"
LOG_SECTION_HEADER = "********"
LOG_SECTION_FOOTER = "********"

# We set min latency variables to MILLISECS_IN_DAY
# to enable simple min latency calculation logic.
MILLISECS_IN_DAY = 86400 * 1000

# Store log fields to parse and do calculations on or display for reference
class LogField:
    """Store log fields to parse and do calculations on or display for reference"""
    def __init__(self, log_key, display_name):
        self.log_key = log_key
        self.display_name = display_name

# Stores pairs of log fields to calculate delta/latency for
class TimingPair:
    """Stores pairs of log fields to calculate delta/latency on"""
    def __init__(self, start_key, end_key, display_name, max_latency):
        self.start_key = start_key
        self.end_key = end_key
        self.display_name = display_name
        self.max_latency = max_latency

# Stores pairs of log fields to calculate delta/latency for
class TimingGroup:
    """
    Stores log field key, log field value, and display name for group to calculate 
    timing on
    """
    def __init__(self, log_field_key, log_field_value, display_name):
        self.log_field_key = log_field_key
        self.log_field_value = log_field_value
        self.display_name = display_name
        self.group_count = 0
        self.total_latency = 0 # Divide by group_count to get avg_latency
        self.min_latency = MILLISECS_IN_DAY
        self.max_latency = 0
        self.avg_latency = 0

class LogEntryTiming:
    """
    Stores the time between two events
    """
    def __init__(self, start_key, end_key, value):
        self.start_key = start_key
        self.end_key = end_key
        self.value = value

class LogEntry:
    """Holds a log entry and associated data"""
    def __init__(self):
        self.valid = True # Whether this is a valid log entry
        self.parse_msg = "" # Store msg from parsing code
        self.full_log_entry = None
        self.log_line = 0 # This log entry's line/position in the performance log
        self.proc_start_time = None # date/time when processing began on this msg/item
        self.fields = {}
        self.timings = {}

class AnalysisSession:
    """Hold the state for a log_analyzer session"""
    perf_log_file_name = None
    perf_log_file_dir = None
    perf_log_file = None
    app_log_file = ''
    excel_results_file = ''
    app_log_file_dir = None
    app_log_file = None
    session_time = None
    verbose = False
    write_to_excel = True 
    logger = None
    xls_doc = None
    log_entry_list = [] # Stores processed perf log entries
    valid_log_entry_count = 0
    invalid_log_entry_count = 0
    log_fields = {}
    timing_pairs = {}
    timing_groups = {}
    total_time = None
    row_header = None
    field_separator = None
    pair_separator = None
    wb = None
    ws_run_info = None
    ws_summary = None
    ws_full_log = None


def load_config(session):
    session.session_time = time.strftime("%Y%m%d-%H%M%S")
    config = configparser.ConfigParser(strict=False)
    config_file_path = os.path.abspath(os.path.dirname(sys.argv[0]))
    config.read_file(open(config_file_path + os.path.sep + "log_analyzer.cfg"))
    session.perf_log_file_name = config.get('perf-log-file', 'perf_log_file_name')
    session.perf_log_file_dir = config.get('perf-log-file', 'perf_log_file_directory')
    session.perf_log_file = session.perf_log_file_dir + os.sep + session.perf_log_file_name
    session.app_log_file = config.get('results-files', 'app_log_file')
    session.excel_results_file = config.get('results-files', 'excel_results_file')
    session.app_log_file_dir = config.get('results-files', 'app_log_file_directory')
    session.app_log_file_name = session.session_time + "-" + session.app_log_file
    session.excel_file_name = session.session_time  + "-" + session.excel_results_file
    session.app_log_file = session.app_log_file_dir + os.sep + session.app_log_file  
    session.row_header = config.get('log-format', 'row_header')
    session.pair_separator = config.get('log-format', 'pair_separator')
    session.field_separator = config.get('log-format', 'field_separator')

    section = 'log-format'
    for option in config.options(section):
        if option.startswith('log_field'):
            log_field_value = config.get(section,option)
            log_field_split = log_field_value.split(':')
            log_field_item = LogField(log_field_split[0],log_field_split[1])
            session.log_fields[log_field_split[0]] = log_field_item
    
    section = 'analysis-reporting'
    for option in config.options(section):
        if option.startswith('timing_pair'):
            timing_pair_value = config.get(section,option)
            timing_pair_split = timing_pair_value.split(':')
            timing_pair_item = TimingPair(timing_pair_split[0],timing_pair_split[1],
                                      timing_pair_split[2],int(timing_pair_split[3]))
            timing_pair_key = timing_pair_split[0] + "-" + timing_pair_split[1]
            session.timing_pairs[timing_pair_key] = timing_pair_item
        elif option.startswith('timing_group'):
            timing_group_value = config.get(section,option)
            timing_group_split = timing_group_value.split(':')
            timing_group_item = TimingGroup(timing_group_split[0],timing_group_split[1],
                                      timing_group_split[2])
            timing_group_key = timing_group_split[0] + "-" + timing_group_split[1]
            session.timing_groups[timing_group_key] = timing_group_item
        elif option.startswith('total_time_pair'):
            timing_pair_value = config.get(section,option)
            timing_pair_split = timing_pair_value.split(':')
            timing_pair_item = TimingPair(timing_pair_split[0],timing_pair_split[1],
                                      timing_pair_split[2],int(timing_pair_split[3]))
            session.total_time = timing_pair_item


# Do basic sanity checking on the app's config and exit if sanity checking fails.
def verify_config(session):
    configVerified = True

    if (not is_file_readable(session.perf_log_file)):
        configVerified = False
        logging.error("File " + session.perf_log_file + " must exist and be readable.")

    if (not is_dir_writable(session.app_log_file_dir)):
        configVerified = False
        logging.error("File " + session.app_log_file_dir + " must exist and be writable.")

    return configVerified


# Read perf log file a line at a time.
def load_performance_log(session):
    session.logger.info("Begin loading performance log")
    successful_load = True
    try:
        with open(session.perf_log_file, 'r') as perf_log:
            line_number = 1
            for line in perf_log:
                parse_log_line(session, line, line_number)
                line_number += 1
    
    except (IOError) as error:
        session.logger.info("Problem reading " + session.perf_log_file + 
                            " Performance log load incomplete.")
        successful_load = False
    finally:
        session.logger.info("End loading performance log")
        return (successful_load == True)


# Parse a line in the perf log file
def parse_log_line(session, log_line, log_line_number):
    try:
        log_entry_is_valid = True
        log_entry = LogEntry()
        log_entry.log_line = log_line_number
        parse_line = log_line.rstrip() # Strip the newline char
        log_entry.full_log_entry = parse_line # Store log entry without new line

        # Check for valid row header
        header_index = parse_line.find(session.row_header)
        if (header_index != -1):
            line_position = header_index + len(session.row_header) + 1
            parse_line = parse_line[line_position:] # Move past header
        else:
            log_entry.valid = False
            session.log_entry_list.append(log_entry)
            session.logger.info("Parsing Note: log line #{} is invalid. Header not found".format(
                str(log_line_number)))
            log_entry.parse_msg += "Header not found, "
            return

        parse_line = parse_line.replace(" ", "") # Remove spaces from line
        split_line = re.split(session.pair_separator, 
                                parse_line) # Split line into key/value pairs
        for item in split_line:
            split_pair = re.split(session.field_separator,
                                    item) # Split pair into key and value
            if (len(split_pair) == 2):
                log_entry.fields[split_pair[0]] = split_pair[1]
            else: # Discard the invalid pair
                session.logger.info("Parsing Note: On log line #{}, discarding invalid Pair: \"{}\"".format(
                    str(log_line_number), item))
                log_entry.parse_msg += "Invalid Pair found, "

        log_entry.valid = (log_entry_is_valid == True)
        session.log_entry_list.append(log_entry)
    except Exception as err:
        session.logger.info("Problem - " + str(err) + " - parsing log line: " + log_line)


def analyze_performance_log(session):

    # Ideally, we'll loop through all the log entries only once, doing all the processing
    # we can in this loop.

    session.logger.info("Starting performance log analysis.")

    try:

        # Set up header row of log details sheet in analysis results doc
        ws_row = 1
        ws_col = 1
        log_line_col = 1
        total_proc_time_col = 2
        parse_msg_col = 3
        analysis_errors_col = 4
        full_log_entry_col = 5
        session.xls_doc.write_cell(session.ws_full_log,ws_row, log_line_col, "Log Line")
        session.xls_doc.write_cell(session.ws_full_log,ws_row, total_proc_time_col, "Total Processing Time")
        session.xls_doc.write_cell(session.ws_full_log,ws_row, parse_msg_col, "Parse Message")
        session.xls_doc.write_cell(session.ws_full_log,ws_row, analysis_errors_col, "Analysis Errors")
        session.xls_doc.write_cell(session.ws_full_log,ws_row, full_log_entry_col, "Full Log Entry")

        for entry in session.log_entry_list:
            if (entry.valid == True):
                session.valid_log_entry_count += 1
            else:
                session.invalid_log_entry_count += 1
                continue # Don't include this log entry in analysis

            ws_row += 1 # Move to a new row to write log entry analysis results.

            err_msgs = "" # Keep all err msgs together and then write to column in xls doc

            # Loop through timing pairs and update vars based on this log entry
            for key in session.timing_pairs:
                start_key = session.timing_pairs[key].start_key
                end_key = session.timing_pairs[key].end_key
                display_name = session.timing_pairs[key].display_name
                max_latency = int(session.timing_pairs[key].max_latency)
                if (start_key in entry.fields and end_key in entry.fields):
                    delta = int(entry.fields[end_key]) - int(entry.fields[start_key])
                    if (delta > max_latency):
                        max_allowed_violation = "Analysis Note: On log line #{}, {} -> {} delta of {} ms exceeds max allowed ({} ms)".format(
                            str(entry.log_line), start_key, end_key, delta, max_latency)
                        session.logger.info(max_allowed_violation)
                        err_msgs += "{} - ".format(max_allowed_violation)
                    entry.timings[key] = LogEntryTiming(start_key, end_key, delta)
                    #print("entry.timings = {}".format(entry.timings))

            # Get the total_time for this entry. We need it for the timing_groups below.
            start_key = session.total_time.start_key
            end_key = session.total_time.end_key
            max_latency = session.total_time.max_latency
            entry_total_proc_time = 0
            if (start_key in entry.fields and end_key in entry.fields):
                delta = int(entry.fields[end_key]) - int(entry.fields[start_key])
                if (delta > max_latency):
                    max_allowed_violation = "Analysis Note: On log line #{}, total time of {} ms exceeds max allowed ({} ms)".format(
                        entry.log_line, delta, max_latency)
                    session.logger.info(max_allowed_violation)
                    err_msgs += "{} - ".format(max_allowed_violation)
                entry.timings["total_time"] = LogEntryTiming(start_key, end_key, delta)
                entry_total_proc_time = entry.timings["total_time"].value
            else: #TODO need to do more to handle this error since using this log entry will result in invalid stats
                total_time_error = "Analysis Error: On log line #{}, cannot calculate total time".format(
                        entry.log_line)
                session.logger.error(total_time_error)
                err_msgs += "{} - ".format(total_time_error)

            # Loop through timing groups and update vars based on this log entry
            for key in session.timing_groups:
                log_field_key = session.timing_groups[key].log_field_key
                log_field_value = session.timing_groups[key].log_field_value
                if (log_field_key in entry.fields):
                    if (entry.fields[log_field_key] == log_field_value):
                        session.timing_groups[key].group_count += 1
                        timing_value = entry.timings["total_time"].value
                        session.timing_groups[key].total_latency += timing_value
                        if (session.timing_groups[key].min_latency > timing_value):
                            session.timing_groups[key].min_latency = timing_value
                        if (session.timing_groups[key].max_latency < timing_value):
                            session.timing_groups[key].max_latency = timing_value
                        #print("Found entry.fields[log_field_key] = {}".format(log_field_value))

            session.xls_doc.write_cell(session.ws_full_log,ws_row, log_line_col, entry.log_line)
            session.xls_doc.write_cell(session.ws_full_log,ws_row, total_proc_time_col, entry_total_proc_time)
            session.xls_doc.write_cell(session.ws_full_log,ws_row, full_log_entry_col, entry.full_log_entry)
            session.xls_doc.write_cell(session.ws_full_log,ws_row, parse_msg_col, entry.parse_msg)
            session.xls_doc.write_cell(session.ws_full_log,ws_row, analysis_errors_col, err_msgs)

            '''
            self.valid = True # Whether this is a valid log entry
            self.parse_msg = "" # Store msg from parsing code
            self.full_log_entry = None
            self.log_line = 0 # This log entry's line/position in the performance log
            self.proc_start_time = None # date/time when processing began on this msg/item
            self.fields = {}
            self.timings = {}
            '''

    except (Exception) as ex:
        session.logger.info("Problem during performance analysis - " + str(ex) + " - Exiting analysis.")

    finally:
        session.logger.info("Completed performance analysis.")


def write_analysis_results(session):

    try:
        analysis_results_header = "***Beginning Analysis Results***"
        session.logger.info(analysis_results_header)

        entries_analyzed = ("{} log entries Analyzed - ".format(str(len(session.log_entry_list))) +
                            "{} valid entries included in analysis - ".format(str(session.valid_log_entry_count)) +
                            "{} invalid entries excluded from analysis".format(str(session.invalid_log_entry_count)))
        session.logger.info(entries_analyzed)
        session.ws_summary.cell(row=1, column=1).value = "Analysis Results Summary"

        ws_row = 3
        ws_col = 1
        session.ws_summary.cell(row=ws_row, column=1).value = "Timing Group"
        session.ws_summary.cell(row=ws_row, column=2).value = "Min Time (ms)"
        session.ws_summary.cell(row=ws_row, column=3).value = "Max Time (ms)"
        session.ws_summary.cell(row=ws_row, column=4).value = "Avg Time (ms)"
        ws_row += 1
        for key in session.timing_groups:
            if (session.timing_groups[key].group_count > 0):
                avg_time = session.timing_groups[key].total_latency / session.timing_groups[key].group_count
                group_report_line_0 = "For timing group \"{}\"".format(session.timing_groups[key].display_name)
                group_report_line_0 += ", min time = {} ms".format(session.timing_groups[key].min_latency)
                group_report_line_0 += ", max time = {} ms".format(session.timing_groups[key].max_latency)
                group_report_line_0 += ", avg time = {:.2f} ms".format(avg_time)
                session.logger.info(group_report_line_0)
                session.ws_summary.cell(row=ws_row, column=1).value = session.timing_groups[key].display_name
                session.ws_summary.cell(row=ws_row, column=2).value = session.timing_groups[key].min_latency
                session.ws_summary.cell(row=ws_row, column=3).value = session.timing_groups[key].max_latency
                session.ws_summary.cell(row=ws_row, column=4).value = "{:.2f}".format(avg_time)
                ws_row += 1
            else:
                group_report_line_0 = "For timing group \"{}\"".format(session.timing_groups[key].display_name)
                group_report_line_0 += ", no records found so no stats calculated"
                session.logger.info(group_report_line_0)

        save_file_name = (session.app_log_file_dir + os.sep + session.session_time
                           + "-" + session.excel_results_file)
        session.xls_doc.save_doc()

    except (Exception) as ex:
        print("Problem during analysis results calculation - " + str(ex) + " - Exiting analyzer.")
        return False

    analysis_results_footer = "***Completed Analysis Results***"
    session.logger.info(analysis_results_footer)


def setup(session):
    ws_row = 1
    ws_col = 1

    try:        
        session.logger = Logger(session.app_log_file_dir, session.app_log_file_name)

        session.xls_doc = XLSDoc(session.app_log_file_dir, session.excel_file_name)
        session.ws_run_info = session.xls_doc.create_worksheet("Run Info", 2)
        session.ws_summary = session.xls_doc.create_worksheet("Analysis Summary", 0)
        session.ws_full_log = session.xls_doc.create_worksheet("Analysis Log", 1)
        session.xls_doc.delete_worksheet("Sheet")

        session.logger.info(LOG_SECTION_HEADER)
        session.logger.info(APP_NAME + " " + APP_VERSION)
        session.ws_run_info.cell(row=1, column=1).value = "App Name"
        session.ws_run_info.cell(row=1, column=2).value = APP_NAME
        session.ws_run_info.cell(row=2, column=1).value = "App version"
        session.ws_run_info.cell(row=2, column=2).value = APP_VERSION
        session.logger.info(WELCOME_MSG)
        session.logger.info(AUTHORS)
        session.ws_run_info.cell(row=3, column=1).value = "Authors"
        session.ws_run_info.cell(row=3, column=2).value = AUTHORS
        session.logger.info(SOURCE_LINK)
        session.ws_run_info.cell(row=4, column=1).value = "Source repo"
        session.ws_run_info.cell(row=4, column=2).value = SOURCE_LINK
        session.logger.info(LOG_SECTION_FOOTER)

        session.logger.info("Analyzer starting. Time is " +
                            session.session_time )
        session.ws_run_info.cell(row=5, column=1).value = "Analyzer start time"
        session.ws_run_info.cell(row=5, column=2).value = session.session_time
        session.xls_doc.save_doc()

        return True
    except (Exception) as ex:
        print("Problem during setup - " + str(ex) + " - Exiting analyzer.")
        return False

def shutdown(session, exitStatus, exitStatusMessage):
    session.logger.info("Analyzer cleaning up ...")
    session.logger.info(exitStatusMessage)
    session.logger.shutdown()
    app_log_file_msg = "App log file for this session is " + session.app_log_file
    print("\n" + app_log_file_msg + "\n")
    sys.exit(exitStatus)


def main():

    session = AnalysisSession()

    load_config(session)
    if (verify_config(session) != True):
        print("\nError loading app configuration. Please check config file. Exiting.\n")
        sys.exit()

    if (setup(session) != True): 
        print("\nError during setup. Exiting.\n")
        sys.exit()

    # Read performance log file and load each log entry
    # for analysis
    if (load_performance_log(session) != True):
        shutdown(session, 0, "Perforpathmance log not loaded. Analyzer exiting")


    if (len(session.log_entry_list) == 0):
        session.logger.info("No log entries suitable for analysis found in log file.")
        shutdown(session, 0, "Analyzer exiting")

    # Analyze the loaded log entries
    analyze_performance_log(session)

    # Write analysis results to log and optionally to stdout
    write_analysis_results(session)

    shutdown(session, 0, "Analyzer exiting")


if __name__ == "__main__":
    main()
