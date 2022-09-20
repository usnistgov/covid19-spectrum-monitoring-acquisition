# python 3
# Version 1.0
"""
    This file takes a SanJole WaveJudge xml output file as input and parses the
    data for the NIST COVID-19 Spectrum Monitoring project. It outputs csv
    files by DCI format containing the raw data useful for the project.
    
    This file also processes the parsed data. It calculates data relevant to 
    the project and outputs csv files for uplink and downlink containing that
    data.
    
    For more information, see the Data Processing Procedure
    
    If you have any questions or concerns, contact 'mattjwr@gmail.com'.
"""

import os
import sys
import csv
import re
import warnings
import time as ti
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from lte_helpers import LTEHelpers

# Global flags
VERBOSE = False

# Constants used in the WJ XML tree structure
DECODE_TREE = 'DecodeTree'
MESSAGE_TAG = 'MessageData'
NODE = 'Node'
NAME = 'Name'
VALUE = 'Value'

# Constants of message names in the WJ tree
DCI_FORMAT_0 = 'DCI Format 0'
DCI_FORMAT_1A = 'DCI Format 1A'
DCI_FORMAT_1B = 'DCI Format 1B'
DCI_FORMAT_1C = 'DCI Format 1C'
DCI_FORMAT_1 = 'DCI Format 1'
DCI_FORMAT_2 = 'DCI Format 2'
DCI_FORMAT_2A = 'DCI Format 2A'
DCI_FORMAT_2C = 'DCI Format 2C'

# DCI information processor classes
class DataProcessor():
    HEADER = ['Time (s)', 'Users', 'RBs', 'Average MCS']

    # Initialize class
    def __init__(self, duration, fileOut, bandwidth):
        self.duration = duration
        self.fileOut = fileOut
        self.bandwidth = bandwidth
        self.rbgToRb = self._set_rb_conversion(bandwidth)
        self.bitLength, self.smallEndBit = self._set_bit_length(bandwidth)
        self.lteHelper = LTEHelpers(bandwidth)
        
        self._reinit(0)
    
    # Reinitialize at the start of each time bin
    def _reinit(self, t):
        self.t0 = t
        self.userCount = 0
        self.rntiList = []
        self.rbCount = 0
        self.totMCS = 0
        self.mcsCount = 0
        self.rbOverflow = False
        self.ueLog = []
    
    # Return the number of RBs in each RBG
    def _set_rb_conversion(self, bandwidth):
        if bandwidth == 6:
            return 1
        elif bandwidth == 15:
            return 2
        elif bandwidth == 25:
            return 2
        elif bandwidth == 50:
            return 3
        elif bandwidth == 75:
            return 4
        elif bandwidth == 100:
            return 4
        else:
            warnings.warn("\n  Bandwidth (in RBs) is not valid.")
            sys.exit(1)
    
    # Return the maximum number of RBGs allocated and whether the last RBG has one less RB
    def _set_bit_length(self, bandwidth):
        if bandwidth == 6:
            return 6, False
        elif bandwidth == 15:
            return 8, True
        elif bandwidth == 25:
            return 13, True
        elif bandwidth == 50:
            return 17, True
        elif bandwidth == 75:
            return 19, True
        elif bandwidth == 100:
            return 25, False
        else:
            warnings.warn("\n  Bandwidth (in RBs) is not valid.")
            sys.exit(1)
    
    # Take the average of the MCS over time bin
    def avg_mcs(self):
        if self.mcsCount == 0:
            warnings.warn("\n  Average MCS dividing by 0. Use the add_mcs function before averaging.")
            return -1
        
        # Return average to 2 decimal places
        avg = self.totMCS*100/self.mcsCount
        avg = round(avg)
        avg = avg/100
        
        return avg
    
    # Write relevant information to processed output file
    def _write(self):
        output = [float(self.t0)/1000, self.userCount, self.rbCount, self.avg_mcs()]
        
        if(self.rbOverflow):
            output += self.ueLog
        
        self.fileOut.writerow(output)
    
    # Determine when a time bin is over
    def check_time(self, timeString):
        timeSplit = timeString.split(':')
        t = (int(timeSplit[0])*3600 + int(timeSplit[1])*60)*1000 + round(float(timeSplit[2])*1000)
        
        if t < self.t0:
            if VERBOSE:
                warnings.warn("\n  Went back in time at time: " + timeString + "\n  Dumping incomplete time bin...")
            self._reinit(t)
        
        if t - self.t0 >= self.duration:
            if not self.t0 == 0:
                self._write()
            
            self._reinit(t)
    
    # Add to the unique UE count
    def add_user(self, rnti):
        if rnti not in self.rntiList:
            self.rntiList.append(rnti)
            self.userCount += 1
    
    # Add to the MCS total
    def add_mcs(self, mcs):
        self.totMCS += mcs
        self.mcsCount += 1

class ULDataProcessor(DataProcessor): # Uplink data processor - DCI Format 0
    HEADER = ['Time (s)', 'Users', 'RIV RBs', 'TX Bits', 'Average MCS', 'Overflow: UE 1 Resource Allocation', 'Overflow: UE 2 ...']

    # Initialize class
    def __init__(self, duration, fileOut, bandwidth):
        super().__init__(duration, fileOut, bandwidth)
    
    # Reinitialize at the start of each time bin
    def _reinit(self, t):
        super()._reinit(t)
        self.txBitCount = 0
    
    # Send data to the appropriate functions
    def process(self, timeString, rnti, alloc, allocType, mcs, q, tbs):
        # Make sure data is in appropriate time bin
        super().check_time(timeString)
        
        # Add UE
        super().add_user(rnti)
        
        # Add MCS
        super().add_mcs(int(mcs))
        
        # Add UE RB allocation
        # > sometimes one or more of these pieces of uplink data are missing. This has only been seen with the uplink data.
        try:
            self._add_allocation(int(alloc), int(allocType), int(mcs), q, tbs)
        except:
            if VERBOSE:
                warnings.warn("Uplink allocation error at " + timeString)
        
        # Keep track of relevant data if overflow is detected in this time bin
        self.ueLog += [alloc]
        
        # Check whether the RB count has exceeded bandwidth limits
        # > the limit is the RB bandwidth for each subframe (1 ms) in the time bin
        if self.rbCount > self.bandwidth*self.duration:
            if VERBOSE:
                warnings.warn("\n  Uplink RBs exceed bandwidth limits at time: " + str(float(self.t0)/1000))
            self.rbOverflow = True
    
    # Convert allocation to RBs and add to count
    def _add_allocation(self, alloc, allocType, mcs, q, tbs):
        rbAlloc = 0
        
        # DCI 0 is almost always allocation type 0
        if allocType == 0:
            # Try MITRE RIV lookup table for RB; calculate RBs if table fails
            # > start rb is currently not in use, but may be important for future projects
            try:
                rbAlloc, rbStart = self.lteHelper.get_ul_format_0_grant(alloc)
            except:
                if VERBOSE:
                    warnings.warn("\n  Resource Allocation " + str(alloc) + " is out of RIV table range. Occured at " + str(float(self.t0)/1000))
                rbAlloc, rbStart = self.lteHelper.riv_to_rb(alloc, self.bandwidth)
        
        elif allocType == 1:
            if VERBOSE:
                warnings.warn("\n  Resource allocation type 1 has not yet been implemented")
        else:
            if VERBOSE:
                warnings.warn("Unknown allocation type " + str(allocType))
        
        # Add RB allocation to count
        self.rbCount += rbAlloc
        
        # Determine TX bits allocated
        self._add_tx_bits(mcs, q, tbs, rbAlloc)
    
    # Calculate TX bits allocated and add to count
    def _add_tx_bits(self, mcs, q, tbs, rbAlloc): 
        if not (q == 'RESERVED' or tbs == 'RESERVED'):
            tbsIndexTable = [0,1,2,3,4,5,6,7,8,9,9,10,11,12,13,14,15,15,16,17,18,19,20,21,22,23,24,25,26]
            tbsIndex = tbsIndexTable[mcs]

            self.txBitCount += self.lteHelper.get_ul_tbs(rbAlloc - 1, tbsIndex)
    
    # Write relevant processed information to uplink file
    def _write(self):
        output = [float(self.t0)/1000, self.userCount, self.rbCount, self.txBitCount, self.avg_mcs()]
        
        # Write additional information if RB limits were exceeded
        if(self.rbOverflow):
            output += self.ueLog
        
        self.fileOut.writerow(output)
    
class DLDataProcessor(DataProcessor):
    HEADER = ['Time (s)', 'Users', 'RBs', 'Average MCS', 'Overflow: UE 1 Resource Allocation Type', 'Overflow: UE 1 Resource Allocation', 'Overflow: UE 1 RB Subset', 'Overflow: UE 2 ...']

    # Initialize class
    def __init__(self, duration, fileOut, bandwidth):
        super().__init__(duration, fileOut, bandwidth)
    
    # Reinitialize at the start of each time bin
    def _reinit(self, t):
        super()._reinit(t)
        #self.bitmapList = []
        
    def process(self, timeString, rnti, alloc, allocType, tb1Mcs, tb2Mcs=0, subset=None):
        # Make sure data is in appropriate time bin
        super().check_time(timeString)
        
        # Add UE
        super().add_user(rnti)
        
        # Add MCS
        super().add_mcs(int(tb1Mcs) + int(tb2Mcs))
        
        # Add UE RB allocation
        alloc = int(alloc)
        if allocType == '0':
            self.add_allocation_type_0(alloc)
        elif allocType == '1':
            self.add_allocation_type_1(alloc, int(subset))
        elif allocType == '2':
            self.add_allocation_type_2(alloc)
        else:
            if VERBOSE:
                warnings.warn("\n  Unrecognized DL allocation type " + allocType + " at time " + timeString)
        
        # Keep track of relevant data if overflow is detected in this time bin
        # > RB subset is relevant for allocation type 1 only
        if(subset == None):
            subset = 'N/A'
        self.ueLog += [allocType, alloc, subset]
        
        # Check whether the RB count has exceeded bandwidth limits
        # > the limit is the RB bandwidth for each subframe (1 ms) in the time bin
        if self.rbCount > self.bandwidth*self.duration:
            if VERBOSE:
                warnings.warn("\n  Downlink RBs exceed bandwidth limits at time: " + str(float(self.t0)/1000))
            self.rbOverflow = True
    
    # Convert type 0 allocation to RBs and add to count
    def add_allocation_type_0(self, alloc):
        # Count RBGs allocated
        rbg = self._count_set_bits(alloc)
        
        # Convert RBGs to RBs
        rbAlloc = rbg*self.rbgToRb
        
        # Correct RB count if last RBG contains fewer RBs and is allocated
        if(self.smallEndBit):
            if(alloc & 1):
                rbAlloc -= 1
        
        # Add RB allocation to count
        self.rbCount += rbAlloc
    
    # Convert type 1 allocation to RBs and add to count
    def add_allocation_type_1(self, alloc, subset):
        # Count RBs allocated
        rbAlloc = self._count_set_bits(alloc)

        self.rbCount += rbAlloc
    
    # Convert type 2 allocation to RBs and add to count
    def add_allocation_type_2(self, alloc):
        # Convert RIV to RBs
        rb_alloc = int(alloc/self.bandwidth) + 1
        
        # Count RBs allocated
        self.rbCount += rb_alloc
    
    # Determine the number of bits set in an integer bitmap
    def _count_set_bits(self, n): 
        setBits = 0
        while (n): 
            setBits += n & 1
            n >>= 1
        return setBits
    
    # Write relevant processed information to downlink file
    def _write(self):
        output = [float(self.t0)/1000, self.userCount, self.rbCount, super().avg_mcs()]
        
        # Write additional information if RB limits were exceeded
        if(self.rbOverflow):
            output += self.ueLog
        
        self.fileOut.writerow(output)

# DCI format parser classes
class DCI_0(): # Valid for DCI Format 0 - Uplink
    RESOURCE_ALLOCATION = "Resource Allocation"
    MCS = 'M-CS-RV Index'
    RESOURCE_ALLOCATION_TYPE = 'Resource allocation type'
    
    HEADER = ['Time (s)', 'RNTI', 'Resource Allocation', 'Resource Allocation Type', 'MCS', 'Q', 'TBS']
    
    # Initialize class instance
    def __init__(self, time, rnti, allocation, atype, mcs, q, tbs):
        self.time = time
        self.rnti = rnti
        self.allocation = allocation
        self.atype = atype
        self.mcs = mcs
        self.q = q
        self.tbs = tbs
    
    # Parse through XML tree and return class instnace with relevant data
    @classmethod
    def parse_data(cls, message, node):
        time = message.get('Time')
        rnti = message.get('RNTI')
        
        message_contents = node.findall(NODE)
        for m in message_contents:
            name = m.get(NAME)
            if name == cls.RESOURCE_ALLOCATION:
                allocation = m.get(VALUE)
            elif name == cls.MCS:
                mcs_line = m.get(VALUE)
            elif name == cls.RESOURCE_ALLOCATION_TYPE:
                atype = m.get(VALUE)
        
        # Parse out the different MCS fields in the message
        # ex: "15 =&gt; Q'_m = 4  I_TBS = 14  rv_idx = 0"
        parsed_mcs = re.sub('[^0-9 ]', '', mcs_line)
        remove_spaces = re.sub(' +',' ', parsed_mcs)
        split = remove_spaces.split(' ')
        
        if len(split) == 2:
            # This case can happen if the Q and TBS values are RESERVED
            mcs = split[0]
            q = 'RESERVED'
            tbs = 'RESERVED'
            rv = split[1]
        else:
            mcs = split[0]
            q = split[1]
            tbs = split[2]
            rv = split[3]
        
        return cls(time, rnti, allocation, atype, mcs, q, tbs)
    
    # Output data
    def to_csv(self):
        return [self.time, self.rnti, self.allocation, self.atype, self.mcs, self.q, self.tbs]

class DCI_1X(): # Valid for DCI Formats 1A, 1B, 1C, 1D - Downlink allocation type 2
    RESOURCE_ALLOCATION = "Resource Allocation"
    MCS = 'MCS'
    
    HEADER = ['Time (s)', 'RNTI', 'Resource Allocation', 'MCS']
    
    # Initialize class instance
    def __init__(self, time, rnti, allocation, mcs):
        self.time = time
        self.rnti = rnti
        self.allocation = allocation
        self.mcs = mcs
    
    # Parse through XML tree and return class instnace with relevant data
    @classmethod
    def parse_data(cls, message, node):
        time = message.get('Time')
        rnti = message.get('RNTI')
        
        message_contents = node.findall(NODE)
        for m in message_contents:
            name = m.get(NAME)
            if name == cls.RESOURCE_ALLOCATION:
                allocation = m.get(VALUE)
            elif name == cls.MCS:
                mcs_line = m.get(VALUE)
        
        # Parse out the different MCS fields in the message
        # ex: "15 =&gt; Q'_m = 4  I_TBS = 14  rv_idx = 0"
        try:
            mcs_match = re.search(r'\d+', mcs_line)
            mcs = mcs_match.group(0)
        except:
            if VERBOSE:
                warnings.warn("\n  No MCS available at time " + time)
            mcs = None
        
        return cls(time, rnti, allocation, mcs)
    
    # Output data
    def to_csv(self):
        return [self.time, self.rnti, self.allocation, self.mcs]

class DCI_1(): # Valid for DCI Format 1 - Downlink allocation type 0 or 1
    RESOURCE_ALLOCATION = "Resource Allocation"
    MCS = 'MCS'
    RESOURCE_ALLOCATION_TYPE = 'Resource Allocation Type'
    SUBSET = 'Selected Resource Blocks Subset'
    
    HEADER = ['Time (s)', 'RNTI', 'Resource Allocation', 'Resource Allocation Type', 'MCS']
    
    # Initialize class instance
    def __init__(self, time, rnti, allocation, atype, mcs, subset):
        self.time = time
        self.rnti = rnti
        self.allocation = allocation
        self.atype = atype
        self.mcs = mcs
        self.subset = subset
    
    # Parse through XML tree and return class instnace with relevant data
    @classmethod
    def parse_data(cls, message, node):
        time = message.get('Time')
        rnti = message.get('RNTI')
        
        subset = None
        
        message_contents = node.findall(NODE)
        for m in message_contents:
            name = m.get(NAME)
            if name == cls.RESOURCE_ALLOCATION:
                allocation = m.get(VALUE)
            elif name == cls.RESOURCE_ALLOCATION_TYPE:
                atype = m.get(VALUE)
            elif name == cls.MCS:
                mcs_line = m.get(VALUE)
            elif name == cls.SUBSET:
                subset = m.get(VALUE)
        
        # Parse out the different MCS fields in the message
        # ex: "15 =&gt; Q'_m = 4  I_TBS = 14  rv_idx = 0"
        try:
            mcs_match = re.search(r'\d+', mcs_line)
            mcs = mcs_match.group(0)
        except:
            if VERBOSE:
                warnings.warn("\n  No MCS available at time " + time)
            mcs = None
        
        return cls(time, rnti, allocation, atype, mcs, subset)
    
    # Output data
    def to_csv(self):
        return [self.time, self.rnti, self.allocation, self.atype, self.subset, self.mcs]

class DCI_2X(): # Valid for DCI Formats 2, 2A, 2B?, 2C? - Downlink allocation type 0 or 1
    RESOURCE_ALLOCATION = "Resource Allocation"
    MCS = 'MCS'
    RESOURCE_ALLOCATION_TYPE = 'Resource Allocation Type'
    TRANSPORT_1 = 'Transport Block 1'
    TRANSPORT_2 = 'Transport Block 2'
    SUBSET = 'Selected Resource Blocks Subset'
    
    HEADER = ['Time (s)', 'RNTI', 'Resource Allocation', 'Resource Allocation Type', 'Resource Block Subset', 'Transport Block 1 MCS', 'Transport Block 2 MCS']
    
    # Initialize class instance
    def __init__(self, time, rnti, allocation, atype, tb1_mcs, tb2_mcs, subset=None):
        self.time = time
        self.rnti = rnti
        self.allocation = allocation
        self.atype = atype
        self.tb1_mcs = tb1_mcs
        self.tb2_mcs = tb2_mcs
        self.subset = subset
    
    # Parse through XML tree and return class instnace with relevant data
    @classmethod
    def parse_data(cls, message, node):
        time = message.get('Time')
        rnti = message.get('RNTI')
        
        subset = None
        
        message_contents = node.findall(NODE)
        for m in message_contents:
            name = m.get(NAME)
            if name == cls.RESOURCE_ALLOCATION:
                allocation = m.get(VALUE)
            elif name == cls.RESOURCE_ALLOCATION_TYPE:
                atype = m.get(VALUE)
            elif name == cls.TRANSPORT_1:
                for v in m.findall(NODE):
                    if v.get(NAME) == cls.MCS:
                        tb1_mcs = v.get(VALUE)
            elif name == cls.TRANSPORT_2:
                for v in m.findall(NODE):
                    if v.get(NAME) == cls.MCS:
                        tb2_mcs = v.get(VALUE)
            elif name == cls.SUBSET:
                subset = m.get(VALUE)
        
        return cls(time, rnti, allocation, atype, tb1_mcs, tb2_mcs, subset)
    
    # Output data
    def to_csv(self):
        return [self.time, self.rnti, self.allocation, self.atype, self.subset, self.tb1_mcs, self.tb2_mcs]

# Parses and processes an input XML file
def parse_file(filepath, duration, bandwidth):
    # Create directory for data
    rootPath = os.path.splitext(filepath)[0]
    if not os.path.exists(rootPath):
        os.mkdir(rootPath)
    
    # Create subdirectory for parsed data
    parsePath = rootPath + r"/parsed/"
    if not os.path.exists(parsePath):
        os.mkdir(parsePath)
    
    # Create output file names
    dci0Filename = parsePath + rootPath + '_' + DCI_FORMAT_0.replace(' ','_') + '.csv'
    dci1AFilename = parsePath + rootPath + '_' + DCI_FORMAT_1A.replace(' ','_') + '.csv'
    dci1BFilename = parsePath + rootPath + '_' + DCI_FORMAT_1B.replace(' ','_') + '.csv'
    dci1CFilename = parsePath + rootPath + '_' + DCI_FORMAT_1C.replace(' ','_') + '.csv'
    dci1Filename = parsePath + rootPath + '_' + DCI_FORMAT_1.replace(' ','_') + '.csv'
    dci2Filename = parsePath + rootPath + '_' + DCI_FORMAT_2.replace(' ','_') + '.csv'
    dci2AFilename = parsePath + rootPath + '_' + DCI_FORMAT_2A.replace(' ','_') + '.csv'
    dci2CFilename = parsePath + rootPath + '_' + DCI_FORMAT_2C.replace(' ','_') + '.csv'
    
    # Open output files
    dci0Fh = open(dci0Filename,'w', newline='')
    dci1AFh = open(dci1AFilename,'w', newline='')
    dci1BFh = open(dci1BFilename,'w', newline='')
    dci1CFh = open(dci1CFilename,'w', newline='')
    dci1Fh = open(dci1Filename,'w', newline='')
    dci2Fh = open(dci2Filename,'w', newline='')
    dci2AFh = open(dci2AFilename,'w', newline='')
    dci2CFh = open(dci2CFilename,'w', newline='')
    
    # Set up csv writer for output files
    dci0Writer = csv.writer(dci0Fh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci1AWriter = csv.writer(dci1AFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci1BWriter = csv.writer(dci1BFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci1CWriter = csv.writer(dci1CFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci1Writer = csv.writer(dci1Fh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci2Writer = csv.writer(dci2Fh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci2AWriter = csv.writer(dci2AFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dci2CWriter = csv.writer(dci2CFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

    # Write file headers
    dci0Writer.writerow(DCI_0.HEADER)
    dci1AWriter.writerow(DCI_1X.HEADER)
    dci1BWriter.writerow(DCI_1X.HEADER)
    dci1CWriter.writerow(DCI_1X.HEADER)
    dci1Writer.writerow(DCI_1.HEADER)
    dci2Writer.writerow(DCI_2X.HEADER)
    dci2AWriter.writerow(DCI_2X.HEADER)
    dci2CWriter.writerow(DCI_2X.HEADER)
    
    # Create subdirectory for processed data
    procPath = rootPath + "/processed/"
    if not os.path.exists(procPath):
        os.mkdir(procPath)
    
    # Set up processed uplink file
    ulFilename = procPath + rootPath + '_UL_Processed.csv'
    ulFh = open(ulFilename, 'w', newline='')
    ulWriter = csv.writer(ulFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    ulWriter.writerow(ULDataProcessor.HEADER)
    ulDataProcessor = ULDataProcessor(duration, ulWriter, bandwidth)
    
    # Set up processed downlink file
    dlFilename = procPath + rootPath + '_DL_Processed.csv'
    dlFh = open(dlFilename, 'w', newline='')
    dlWriter = csv.writer(dlFh, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    dlWriter.writerow(DLDataProcessor.HEADER)
    dlDataProcessor = DLDataProcessor(duration, dlWriter, bandwidth)
    
    # Set of data types present in file, but skipped in processing
    skipTypes = set()
    
    # XML tree parser
    parser = ET.iterparse(filepath)
    
    # Look into each message tree
    for event, element in parser:
        # If there are no items for this message, just go to the next one       
        if element.tag == DECODE_TREE:
            message = element
        else:
            continue
        
        time = message.get('Time')
        rnti = message.get('RNTI')
        
        # Iterate through all the sub-messages
        for node in message.findall(NODE):
            # Data type/format (DCI format, MAC message, etc.)
            name = node.get(NAME)
            
            # Parse data and write
            if name == DCI_FORMAT_0:
                dataOut = DCI_0.parse_data(message, node)
                csvOut = dataOut.to_csv()
                ulDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], csvOut[3], csvOut[4], csvOut[5], csvOut[6])
                dci0Writer.writerow(csvOut)
            elif name == DCI_FORMAT_1A:
                dataOut = DCI_1X.parse_data(message, node)
                csvOut = dataOut.to_csv()
                if not csvOut[3]: # > sometimes DCI 1A does not have MCS data. May be true for other formats as well.
                    continue
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], '2', csvOut[3])
                dci1AWriter.writerow(csvOut)
            elif name == DCI_FORMAT_1B:
                dataOut = DCI_1X.parse_data(message, node)
                csvOut = dataOut.to_csv()
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], '2', csvOut[3])
                dci1BWriter.writerow(csvOut)
            elif name == DCI_FORMAT_1C:
                dataOut = DCI_1X.parse_data(message, node)
                csvOut = dataOut.to_csv()
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], '2', csvOut[3])
                dci1CWriter.writerow(csvOut)
            elif name == DCI_FORMAT_1:
                dataOut = DCI_1.parse_data(message, node)
                csvOut = dataOut.to_csv()
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], csvOut[3], csvOut[5], subset=csvOut[4])
                dci2Writer.writerow(csvOut)
            elif name == DCI_FORMAT_2:
                dataOut = DCI_2X.parse_data(message, node)
                csvOut = dataOut.to_csv()
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], csvOut[3], csvOut[5], csvOut[6], subset=csvOut[4])
                dci2Writer.writerow(csvOut)
            elif name == DCI_FORMAT_2A:
                dataOut = DCI_2X.parse_data(message, node)
                csvOut = dataOut.to_csv()
                dlDataProcessor.process(csvOut[0], csvOut[1], csvOut[2], csvOut[3], csvOut[5], csvOut[6], subset=csvOut[4])
                dci2AWriter.writerow(csvOut)
            else:
                # Notify user about data types we don't process
                if VERBOSE:
                    warnings.warn("\n  Cannot process the following data type: " + name + "\n  Skipping data of this type...")
                else:
                    skipTypes.add(name)
    
        element.clear()

    # Close output files
    dci0Fh.close()
    dci1AFh.close()
    dci1BFh.close()
    dci1CFh.close()
    dci1Fh.close()
    dci2Fh.close()
    dci2AFh.close()
    dci2CFh.close()

    ulFh.close()
    dlFh.close()
    
    # List skipped data types
    if not VERBOSE:
        print("The following data types were present in the input file, but skipped in processing:")
        print(skipTypes)

# Convert bandwidth in MHz to RBs
def mhz_to_rb(mhz):
    mhz = round(mhz)
    
    if mhz == 1: # 1.4 MHz
        return 6
    elif mhz == 3:
        return 15
    elif mhz == 5:
        return 25
    elif mhz == 10:
        return 50
    elif mhz == 15:
        return 75
    elif mhz == 20:
        return 100
    else:
        warnings.warn("\n  Bandwidth (in MHz) is not valid.")
        sys.exit(1)

if __name__ == '__main__':
    # Parse input arguments
    parser = ArgumentParser(description="Parse a SanJole wavejudge .xml output file. Made for SSM at NIST.")
    parser.add_argument("-f", "--file", type=str,
                        help="File to parse to CSV")
    parser.add_argument("-d", "--duration", type=float, default=1,
                        help="Length of time bin (milliseconds). Default is 1")
    parser.add_argument('-b', '--bandwidth', default=10, type=float,
                        help='Bandwidth in MHz. Default is 10')
    parser.add_argument('-bRB', '--RBbandwidth', type=int,
                        help='Bandwidth in terms of resource blocks. Overrides bandwidth if set')
    parser.add_argument('-v', '--verbose', action="store_true",
                        help='Enable all warning messages')
    
    args = parser.parse_args()
    
    # Check input file
    if not args.file:
        print('Please specify file')
        sys.exit(1)
        
    if not os.path.splitext(args.file)[1] == '.xml':
        print('The input file must be an xml file')
        sys.exit(1)
    
    # Set verbosity
    if args.verbose:
        VERBOSE = True
    
    # Get RB bandwidth
    if args.RBbandwidth:
        bandwidth = args.RBbandwidth
    else:
        bandwidth = mhz_to_rb(args.bandwidth)
    
    # Parse input file
    tic = ti.time()
    parse_file(args.file, args.duration, bandwidth)
    toc = ti.time()
    print("Time passed: ", toc - tic, " seconds")
    
    sys.exit(0)
