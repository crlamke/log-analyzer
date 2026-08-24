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
from dateutil import parser as dtparser
import argparse

from log_util import *
from fs_util import *
from excel_util import *

APP_NAME = "Log Analyzer"
APP_VERSION = "v0.1"
WELCOME_MSG = "Welcome to the Log Analyzer"
AUTHORS = "Chris Lamke`"
SOURCE_LINK = "https://github.com/crlamke/log-analyzer"
LOG_SECTION_HEADER = "********"
LOG_SECTION_FOOTER = "********"

# We set min latency variables to MILLISECS_IN_DAY
# to enable simple min latency calculation logic.
# This assumes you won't be dealing with latency
# greater than 24 hours.
MILLISECS_IN_DAY = 86400 * 1000

# Stores log fields to parse and do calculations on or display for reference
class LogField:
    """Store log fields to parse and do calculations on or display for reference"""
    def __init__(self, log_key, display_name):
        self.log_key = log_key
        self.display_name = display_name

# Stores pairs of log fields to calculate delta/latency
class TimingPair:
    """Stores pairs of log fields to calculate delta/latency on"""
    def __init__(self, start_key, end_key, display_name, max_allowed_latency):
        self.start_key = start_key
        self.end_key = end_key
        self.display_name = display_name
        self.max_allowed_latency = max_allowed_latency
        self.group_count = 0
        self.total_latency = 0 # Divide by group_count to get avg_latency
        self.min_latency = MILLISECS_IN_DAY
        self.max_latency = 0
        self.avg_latency = 0

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
        self.timestamp = None
        self.fields = {}
        self.timings = {}

class AnalysisSession:
    """Hold the state for a log_analyzer session"""

    def __init__(self):
        self.config_file_full_path = ''
        self.use_cli_config_file = False
        self.log_file_to_analyze_base_name = ''
        self.log_file_to_analyze_directory = ''
        self.log_file_to_analyze_full_name = ''
        self.analysis_results_log_base_name = ''
        self.analysis_results_excel_doc_base_name = ''
        self.analysis_results_directory = ''
        self.analysis_results_log_full_name = ''
        self.analysis_results_excel_doc_full_name = ''
        #app_log_file = None
        self.session_time = None
        self.verbose = False
        self.logger = None
        self.xls_doc = None
        self.log_entry_list = [] # Stores processed perf log entries
        self.valid_log_entry_count = 0
        self.invalid_log_entry_count = 0
        self.filter_exclusion_count = 0
        self.log_fields = {}
        self.timing_pairs = {}
        self.timing_groups = {}
        self.total_time = None
        self.read_timestamps = True
        self.filter_on_timestamps = False
        self.filter_start_time = None
        self.filter_end_time = None
        self.row_header = None
        self.field_separator = None
        self.pair_separator = None
        self.wb = None
        self.ws_run_info = None
        self.ws_summary = None
        self.ws_full_log = None
        self.left_header_format = None
        self.top_header_format = None
        self.data_format = None
        self.page_header_format = None
        self.serious_errors = ""


def load_config(session):
    try:
        session.session_time = time.strftime("%Y%m%d-%H%M%S")
        config = configparser.ConfigParser(strict=False)
        if (session.use_cli_config_file == False):
            config_file_path = (os.path.abspath(os.path.dirname(sys.argv[0])) 
                                + os.path.sep + "log_analyzer.cfg")
        else:
            config_file_path = session.config_file_full_path

        config.read_file(open(config_file_path))
        session.log_file_to_analyze_base_name = config.get('log-file-to-analyze', 'log_file_to_analyze_base_name')
        session.log_file_to_analyze_directory = config.get('log-file-to-analyze', 'log_file_to_analyze_directory')
        session.log_file_to_analyze_full_name = (session.log_file_to_analyze_directory + os.path.sep + 
                                                session.log_file_to_analyze_base_name)
        session.analysis_results_log_base_name = (session.session_time + "-" + 
                                            config.get('analysis-results-files', 'analysis_results_log_base_name'))
        session.analysis_results_excel_doc_base_name = (session.session_time + "-" + 
                                    config.get('analysis-results-files', 'analysis_results_excel_doc_base_name'))
        session.analysis_results_directory = config.get('analysis-results-files', 'analysis_results_directory')
        session.analysis_results_log_full_name = (session.analysis_results_directory + os.path.sep + 
                                                session.analysis_results_log_base_name)
        session.analysis_results_excel_doc_full_name = (session.analysis_results_directory + os.path.sep + 
                                                session.analysis_results_excel_doc_base_name)
        session.row_header = config.get('log-format', 'row_header')
        session.pair_separator = config.get('log-format', 'pair_separator')
        session.field_separator = config.get('log-format', 'field_separator')

        read_timestamps_string = config.get('timestamps', 'read_timestamps')
        session.read_timestamps = (read_timestamps_string.lower() == "true")
        if (session.read_timestamps == True):
            filter_on_timestamps_string = config.get('timestamps', 'filter_on_timestamps')
            session.filter_on_timestamps = (filter_on_timestamps_string.lower() == "true")
            session.filter_start_time = dtparser.parse(config.get('timestamps', 'filter_start_time'))
            session.filter_end_time = dtparser.parse(config.get('timestamps', 'filter_end_time'))

        section = 'log-format'
        for option in config.options(section):
            if option.startswith('log_field'):
                log_field_value = config.get(section,option)
                log_field_split = log_field_value.split(':')
                log_field_item = LogField(log_field_split[0],log_field_split[1])
                session.log_fields[log_field_split[0]] = log_field_item

        section = 'timing-pairs'
        for option in config.options(section):
            if option.startswith('timing_pair'):
                timing_pair_value = config.get(section,option)
                timing_pair_split = timing_pair_value.split(':')
                timing_pair_item = TimingPair(timing_pair_split[0],timing_pair_split[1],
                                        timing_pair_split[2],int(timing_pair_split[3]))
                timing_pair_key = timing_pair_split[0] + "-" + timing_pair_split[1]
                session.timing_pairs[timing_pair_key] = timing_pair_item

        section = 'total-time-pair'
        for option in config.options(section):
            if option.startswith('total_time_pair'):
                timing_pair_value = config.get(section,option)
                timing_pair_split = timing_pair_value.split(':')
                timing_pair_item = TimingPair(timing_pair_split[0],timing_pair_split[1],
                                        timing_pair_split[2],int(timing_pair_split[3]))
                session.total_time = timing_pair_item

        section = 'timing-groups'
        for option in config.options(section):
            if option.startswith('timing_group'):
                timing_group_value = config.get(section,option)
                timing_group_split = timing_group_value.split(':')
                timing_group_item = TimingGroup(timing_group_split[0],timing_group_split[1],
                                        timing_group_split[2])
                timing_group_key = timing_group_split[0] + "-" + timing_group_split[1]
                session.timing_groups[timing_group_key] = timing_group_item

        section = 'counting-groups'
        for option in config.options(section):
            if option.startswith('counting_group'):
                timing_group_value = config.get(section,option)
                timing_group_split = timing_group_value.split(':')
                timing_group_item = TimingGroup(timing_group_split[0],timing_group_split[1],
                                        timing_group_split[2])
                timing_group_key = timing_group_split[0] + "-" + timing_group_split[1]
                session.timing_groups[timing_group_key] = timing_group_item
    except (IOError, configparser.Error, IndexError, ValueError) as error:
        print("Problem loading options from config file - " + str(error))
        if session.logger:
            session.logger.info("Problem loading options from config file - " + str(error))
        return False

    return True

# Do basic sanity checking on the app's config and exit if sanity checking fails.
def verify_config(session):
    configVerified = True

    if (not is_file_readable(session.log_file_to_analyze_full_name)):
        configVerified = False
        logging.error("File " + session.log_file_to_analyze_full_name + " must exist and be readable.")

    if (not is_dir_writable(session.analysis_results_directory)):
        configVerified = False
        logging.error("File " + session.analysis_results_directory + " must exist and be writable.")

    return configVerified


# Read logfile a line at a time.
def parse_log_file(session):
    session.logger.info("Begin loading performance log")
    successful_load = True
    try:
        with open(session.log_file_to_analyze_full_name, 'r') as logfile:
            line_number = 1
            for line in logfile:
                parse_log_line(session, line, line_number)
                line_number += 1

    except (IOError) as error:
        session.logger.info("Problem reading " + session.log_file_to_analyze_full_name + 
                            ". Logfile load incomplete.")
        successful_load = False
    finally:
        session.logger.info("End load of logfile")
        return (successful_load == True)


# Parse a line in the logfile
def parse_log_line(session, log_line, log_line_number):
    try:
        log_entry_is_valid = True
        log_entry = LogEntry()
        log_entry.log_line = log_line_number
        parse_line = log_line.rstrip() # Strip the newline char
        log_entry.full_log_entry = parse_line # Store log entry without new line

        # Check for valid ISO-8601 datetime at start of header
        # Split line at first space - should split datetime from rest of log entry line
        if (session.read_timestamps == True):
            split_line = parse_line.split(' ', 1)
            date_time = split_line[0]
            parse_line = split_line[1]
            log_entry.timestamp = dtparser.parse(date_time).replace(microsecond=0)
            
            # Check if we should filter on timestamps and if so, do comparison
            # and skip line if it fails filter
            if (session.filter_on_timestamps == True):
                if ((log_entry.timestamp < session.filter_start_time) or 
                    (log_entry.timestamp > session.filter_end_time)):
                        session.filter_exclusion_count += 1
                        return # log entry timstamp fails filter so exclude it

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
            log_entry.parse_msg += "Header not found"
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
                if (log_entry.parse_msg == ""):
                    log_entry.parse_msg += "Invalid Pair found ({}) ".format(item)
                else:
                    log_entry.parse_msg += ", Invalid Pair found ({}) ".format(item)

        log_entry.valid = (log_entry_is_valid == True)
        session.log_entry_list.append(log_entry)
    except Exception as err:
        session.logger.info("Problem - " + str(err) + " - parsing log line: " + log_line)


def analyze_log_file(session):

    # Ideally, we'll loop through all the log entries only once, doing all the processing
    # we can in this loop.

    session.logger.info("Starting logfile analysis.")

    try:
        # Set up header row of log details sheet in analysis results doc
        log_field_count = len(session.log_fields)
        ws_row = 1
        timestamp_col = 0 

        col_offset = 1 # We'll increment this based on whether we add conditional columns 
        log_line_col = col_offset
        col_offset += 1
        if (session.read_timestamps == True):
            timestamp_col = col_offset
            col_offset += 1
        total_proc_time_col = col_offset
        col_offset += 1
        log_field_start_offset = col_offset
        col_offset += log_field_count
        parse_msgs_col = col_offset
        col_offset += 1
        analysis_notes_col = col_offset
        col_offset += 1
        full_log_entry_col = col_offset
        #col_offset += 1 # Increment col_offset if we want to add another column to the worksheet
        session.xls_doc.write_cell(session.ws_full_log, ws_row, log_line_col, "Log Line", session.top_header_format)
        if (session.read_timestamps == True):
            session.xls_doc.write_cell(session.ws_full_log, ws_row, timestamp_col, "Timestamp",
                                       session.top_header_format)
        session.xls_doc.write_cell(session.ws_full_log, ws_row, total_proc_time_col, "Total Processing Time",
                                    session.top_header_format)
        log_field_col = log_field_start_offset
        for field in session.log_fields:
            col_name = session.log_fields[field].display_name
            session.xls_doc.write_cell(session.ws_full_log,ws_row, log_field_col, col_name, 
                                   session.top_header_format)
            log_field_col += 1

        session.xls_doc.write_cell(session.ws_full_log,ws_row, parse_msgs_col, "Parse Messages", 
                                   session.top_header_format)
        session.xls_doc.write_cell(session.ws_full_log,ws_row, analysis_notes_col, "Analysis Notes", 
                                   session.top_header_format)
        session.xls_doc.write_cell(session.ws_full_log,ws_row, full_log_entry_col, "Full Log Entry", 
                                   session.top_header_format)

        for entry in session.log_entry_list:
            if (entry.valid == True):
                session.valid_log_entry_count += 1
            else:
                session.invalid_log_entry_count += 1
                continue # Don't include this log entry in analysis

            ws_row += 1 # Move to a new row to write log entry analysis results.

            try:
                err_msgs = "" # Keep all err msgs together and then write to column in xls doc

                # Loop through timing pairs and update vars based on this log entry
                for key in session.timing_pairs:
                    # First, search for the two keys that make up the timing pair in this
                    # log entry. If they're not both present, we continue to the next key.
                    # Note: Using an if to check for presence of start and end keys because
                    # dictionaries throw exception on not found.
                    start_key = session.timing_pairs[key].start_key
                    end_key = session.timing_pairs[key].end_key
                    if (start_key in entry.fields and end_key in entry.fields):
                        start_time = entry.fields[start_key]
                        end_time = entry.fields[end_key]
                    else:
                        continue

                    # Next, calculate the time between the first and second event defined
                    # by the keys and compare it against the min_latency and max_latency,
                    # and add it to the total latency and increase the count of entries
                    # with this timing_pair so we can display that and also use it to
                    # calculate the avg latency for reporting.
                    timing_value = int(end_time) - int(start_time)
                    session.timing_pairs[key].group_count += 1
                    session.timing_pairs[key].total_latency += timing_value
                    if (session.timing_pairs[key].min_latency > timing_value):
                        session.timing_pairs[key].min_latency = timing_value
                    if (session.timing_pairs[key].max_latency < timing_value):
                        session.timing_pairs[key].max_latency = timing_value

                # Get the total_time for this entry. We need it for the timing_groups below.
                start_key = session.total_time.start_key
                end_key = session.total_time.end_key
                max_allowed_latency = session.total_time.max_allowed_latency
                entry_total_proc_time = 0
                have_total_time = False
                if (start_key in entry.fields and end_key in entry.fields):
                    delta = int(entry.fields[end_key]) - int(entry.fields[start_key])
                    if (delta > max_allowed_latency):
                        max_allowed_violation = "Analysis Note: On log line #{}, total time of {} ms exceeds max allowed ({} ms)".format(
                            entry.log_line, delta, max_allowed_latency)
                        session.logger.info(max_allowed_violation)
                        err_msgs += "{} - ".format(max_allowed_violation)
                    entry.timings["total_time"] = LogEntryTiming(start_key, end_key, delta)
                    entry_total_proc_time = entry.timings["total_time"].value
                    have_total_time = True
                else: #TODO need to do more to handle this error since using this log entry will result in invalid stats
                    total_time_error = "Analysis Error: On log line #{}, cannot calculate total time".format(
                            entry.log_line)
                    session.logger.error(total_time_error)
                    err_msgs += "{} - ".format(total_time_error)
                    add_serious_error(session, total_time_error)

                # Loop through timing groups and update vars based on this log entry
                if have_total_time:
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

                session.xls_doc.write_cell(session.ws_full_log,ws_row, log_line_col, entry.log_line)
                session.xls_doc.write_cell(session.ws_full_log,ws_row, total_proc_time_col, entry_total_proc_time)
                if (session.read_timestamps == True):
                    timestamp_str = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
                    session.ws_full_log.cell(row=ws_row, column=timestamp_col).number_format = numbers.FORMAT_TEXT
                    session.xls_doc.write_cell(session.ws_full_log, ws_row, timestamp_col, 
                                               timestamp_str)
                log_field_col = log_field_start_offset
                for field in session.log_fields:
                    col_value = entry.fields.get(session.log_fields[field].log_key,"null")
                    session.xls_doc.write_cell(session.ws_full_log,ws_row, log_field_col, col_value, 
                                       session.data_format)
                    log_field_col += 1
                session.xls_doc.write_cell(session.ws_full_log,ws_row, full_log_entry_col, entry.full_log_entry)
                session.xls_doc.write_cell(session.ws_full_log,ws_row, parse_msgs_col, entry.parse_msg)
                session.xls_doc.write_cell(session.ws_full_log,ws_row, analysis_notes_col, err_msgs)

            except (Exception) as entry_ex:
                session.logger.info("Problem analyzing log entry on log line #{} - {} - skipping this entry.".format(
                    entry.log_line, str(entry_ex)))
                add_serious_error(session, "Analysis Error: On log line #{}, entry could not be analyzed ({})".format(
                    entry.log_line, str(entry_ex)))
                continue

    except (Exception) as ex:
        session.logger.info("Problem during logfile analysis - " + str(ex) + " - Exiting analysis.")

    finally:
        session.logger.info("Completed logfile analysis.")


def write_analysis_results(session):

    try:
        analysis_results_header = "***Beginning Analysis Results***"
        session.logger.info(analysis_results_header)

        total_entries_analyzed = str(len(session.log_entry_list))
        valid_entries = str(session.valid_log_entry_count)
        invalid_entries = str(session.invalid_log_entry_count)
        excluded_entries = str(session.filter_exclusion_count)
        entries_analyzed = ("{} log entries Analyzed - ".format(total_entries_analyzed) +
                            "{} valid entries included in analysis - ".format(valid_entries) +
                            "{} invalid entries excluded from analysis - ".format(invalid_entries) +
                            "{} Entries excluded by filter".format(excluded_entries))
        session.logger.info(entries_analyzed)

        serious_errors = session.serious_errors
        if (serious_errors == ""):
            serious_errors = "None"
        session.logger.info("Serious errors: {}".format(serious_errors))

        # Make call to underlying openpyxl lib to merge cells
        session.ws_summary.merge_cells('A1:E1')
        session.xls_doc.write_cell(session.ws_summary,1, 1, "Analysis Results Summary", session.page_header_format)
        session.xls_doc.write_cell(session.ws_summary,3, 1, "Log Entries Analyzed", session.left_header_format)
        session.xls_doc.write_cell(session.ws_summary,3, 2, total_entries_analyzed, session.data_format)
        session.xls_doc.write_cell(session.ws_summary,4, 1, "Valid Entries", session.left_header_format)
        session.xls_doc.write_cell(session.ws_summary,4, 2, valid_entries, session.data_format)
        session.xls_doc.write_cell(session.ws_summary,5, 1, "Invalid Entries (Discarded)", session.left_header_format)
        session.xls_doc.write_cell(session.ws_summary,5, 2, invalid_entries, session.data_format)
        session.xls_doc.write_cell(session.ws_summary,6, 1, "Entries excluded by filter", session.left_header_format)
        session.xls_doc.write_cell(session.ws_summary,6, 2, session.filter_exclusion_count, session.data_format)
        session.xls_doc.write_cell(session.ws_summary,8, 1, "Serious Errors During Analysis", session.left_header_format)
        session.xls_doc.write_cell(session.ws_summary,8, 2, serious_errors, session.data_format)
        serious_errors_note = "Note: Serious errors are errors that could affect the integrity of all analysis results"
        session.xls_doc.write_cell(session.ws_summary,8, 3, serious_errors_note, session.data_format)

        ws_row = 10
        ws_col = 1
        session.xls_doc.write_cell(session.ws_summary,ws_row, 1, "Timing Group", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 2, "Count", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 3, "Min Time (ms)", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 4, "Max Time (ms)", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 5, "Avg Time (ms)", session.top_header_format)
        ws_row += 1
        for key in session.timing_groups:
            if (session.timing_groups[key].group_count > 0):
                avg_time = session.timing_groups[key].total_latency / session.timing_groups[key].group_count
                group_report_line_0 = "For timing group \"{}\"".format(session.timing_groups[key].display_name)
                group_report_line_0 += ", min time = {} ms".format(session.timing_groups[key].min_latency)
                group_report_line_0 += ", max time = {} ms".format(session.timing_groups[key].max_latency)
                group_report_line_0 += ", avg time = {:.2f} ms".format(avg_time)
                session.logger.info(group_report_line_0)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 1, session.timing_groups[key].display_name)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 2, session.timing_groups[key].group_count)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 3, session.timing_groups[key].min_latency)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 4, session.timing_groups[key].max_latency)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 5, "{:.2f}".format(avg_time))
                ws_row += 1
            else:
                group_report_line_0 = "For timing group \"{}\"".format(session.timing_groups[key].display_name)
                group_report_line_0 += ", no records found so no stats calculated"
                session.logger.info(group_report_line_0)

        ws_row += 1
        session.xls_doc.write_cell(session.ws_summary,ws_row, 1, "Timing Pair", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 2, "Count", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 3, "Min Time (ms)", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 4, "Max Time (ms)", session.top_header_format)
        session.xls_doc.write_cell(session.ws_summary,ws_row, 5, "Avg Time (ms)", session.top_header_format)
        ws_row += 1
        for key in session.timing_pairs:
            if (session.timing_pairs[key].group_count > 0):
                avg_time = session.timing_pairs[key].total_latency / session.timing_pairs[key].group_count
                group_report_line_0 = "For timing pair \"{}\"".format(session.timing_pairs[key].display_name)
                group_report_line_0 += ", min time = {} ms".format(session.timing_pairs[key].min_latency)
                group_report_line_0 += ", max time = {} ms".format(session.timing_pairs[key].max_latency)
                group_report_line_0 += ", avg time = {:.2f} ms".format(avg_time)
                session.logger.info(group_report_line_0)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 1, session.timing_pairs[key].display_name)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 2, session.timing_pairs[key].group_count)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 3, session.timing_pairs[key].min_latency)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 4, session.timing_pairs[key].max_latency)
                session.xls_doc.write_cell(session.ws_summary,ws_row, 5, "{:.2f}".format(avg_time))
                ws_row += 1
            else:
                group_report_line_0 = "For timing pair \"{}\"".format(session.timing_pairs[key].display_name)
                group_report_line_0 += ", no records found so no stats calculated"
                session.logger.info(group_report_line_0)

        session.xls_doc.save_doc()

    except (Exception) as ex:
        print("Problem during analysis results calculation - " + str(ex) + " - Exiting analyzer.")
        return False

    analysis_results_footer = "***Completed Analysis Results***"
    session.logger.info(analysis_results_footer)

def add_serious_error(session, serious_error):
    if (session.serious_errors == ""):
        session.serious_errors = serious_error
    else:
        session.serious_errors += "; " + serious_error

def setup(session):
    try:
        setup_logger(session)
        setup_xls_doc(session)

        return True
    except (Exception) as ex:
        print("Problem during setup - " + str(ex) + " - Exiting analyzer.")
        return False

def setup_logger(session):
    try:    
        session.logger = Logger(session.analysis_results_directory, 
        session.analysis_results_log_base_name)

        session.logger.info(LOG_SECTION_HEADER)
        session.logger.info(WELCOME_MSG)
        session.logger.info("App Name: " + APP_NAME + " " + APP_VERSION)
        session.logger.info("Authors: " + AUTHORS)
        session.logger.info("Source code at " + SOURCE_LINK)
        session.logger.info(LOG_SECTION_FOOTER)
        session.logger.info("Analyzer starting. Time is " +
                            session.session_time )
    except (Exception) as ex:
        print("Problem during logger setup - " + str(ex) + " - Exiting analyzer.")
        return False

def setup_xls_doc(session):
    try:
        session.left_header_format = XLSCellFormat()
        session.left_header_format.font_size = 12
        session.left_header_format.is_bold = True
        session.left_header_format.horiz_align = 'left'
        session.left_header_format.vert_align = 'top'
        session.left_header_format.create_format()
        session.top_header_format = XLSCellFormat()
        session.top_header_format.font_size = 13
        session.top_header_format.is_bold = True
        session.top_header_format.horiz_align = 'center'
        session.top_header_format.vert_align = 'top'
        session.top_header_format.create_format()
        session.page_header_format = XLSCellFormat()
        session.page_header_format.font_size = 14
        session.page_header_format.is_bold = True
        session.page_header_format.horiz_align = 'center'
        session.page_header_format.vert_align = 'top'
        session.page_header_format.create_format()

        session.data_format = XLSCellFormat()
        session.data_format.create_format()
        session.xls_doc = XLSDoc(session.analysis_results_directory, 
                                 session.analysis_results_excel_doc_base_name)
        session.ws_summary = session.xls_doc.create_worksheet("Analysis Summary", 0)
        session.ws_full_log = session.xls_doc.create_worksheet("Analysis Log", 1)
        session.ws_run_info = session.xls_doc.create_worksheet("Run Info", 2)
        session.xls_doc.delete_worksheet("Sheet")
        session.xls_doc.write_cell(session.ws_run_info,1, 1, "App Name", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,1, 2, APP_NAME)
        session.xls_doc.write_cell(session.ws_run_info,2, 1, "App version", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,2, 2, APP_VERSION)
        session.xls_doc.write_cell(session.ws_run_info,3, 1, "Authors", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,3, 2, AUTHORS)
        session.xls_doc.write_cell(session.ws_run_info,4, 1, "Source repo", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,4, 2, SOURCE_LINK)
        session.xls_doc.write_cell(session.ws_run_info,5, 1, "Analyzer start time", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,5, 2, session.session_time)
        session.xls_doc.write_cell(session.ws_run_info,6, 1, "Log File Analyzed", session.left_header_format)
        session.xls_doc.write_cell(session.ws_run_info,6, 2, session.log_file_to_analyze_full_name)

        session.xls_doc.save_doc()

        return True
    except (Exception) as ex:
        print("Problem during XLS doc setup - " + str(ex) + " - Exiting analyzer.")
        return False

def parse_command_line(session):
    try:
        if (len(sys.argv) == 2):
            session.config_file_full_path = sys.argv[1]
            if (not is_file_readable(session.config_file_full_path)):
                print("Problem verifying ability to read config file.")
                return False
            else:
                session.use_cli_config_file = True
                print("Will use config file passed to " + sys.argv[0] + ": " +
                      session.config_file_full_path)
        else:
            print("No arguments passed to " + sys.argv[0] + ".")
            session.use_cli_config_file = False # Set to False since user didn't pass cfg file on command line.

        return True
    except (Exception) as ex:
        print("Problem during command line parsing - " + str(ex) + " - Exiting analyzer.")
        return False

def shutdown(session, exitStatus, exitStatusMessage):
    session.logger.info("Analyzer cleaning up ...")
    session.logger.info(exitStatusMessage)
    session.logger.shutdown()
    app_log_file_msg = "App log file for this session is " + session.analysis_results_log_full_name
    print("\n" + app_log_file_msg + "\n")
    sys.exit(exitStatus)


def main():
    session = AnalysisSession()

    if (parse_command_line(session) != True):
        print("\nFailure during command line parsing. Analyzer exiting.\n")
        sys.exit()

    if (load_config(session) != True):
        print("\nError loading app configuration. Please check config file. Exiting.\n")
        sys.exit()

    if (verify_config(session) != True):
        print("\nError loading app configuration. Please check config file. Exiting.\n")
        sys.exit()

    if (setup(session) != True): 
        print("\nError during setup. Exiting.\n")
        sys.exit()

    # Read performance log file and load each log entry
    # for analysis
    if (parse_log_file(session) != True):
        shutdown(session, 0, "Failed to load log to analyze. Analyzer exiting")

    if (len(session.log_entry_list) == 0):
        session.logger.info("No log entries suitable for analysis found in log file.")
        shutdown(session, 0, "Analyzer exiting")

    # Analyze the loaded log entries
    analyze_log_file(session)

    # Write analysis results to log and optionally to stdout
    write_analysis_results(session)

    shutdown(session, 0, "Analyzer exiting")


if __name__ == "__main__":
    main()
