###############################################################################
# This software was produced for the U. S. Government under Basic Contract No.#
# W56KGU-18-D-0004, and is subject to the Rights in Noncommercial Computer    # 
# Software and Noncommercial Computer Software Documentation Clause           #
# 252.227-7014 (FEB 2012) 2019 The MITRE Corporation.                         #
###############################################################################

import csv
import math
import os


class LTEHelpers:

    ABSOLUTE_SUBFRAME_MAX = 102399

    def __init__(self, nulrb=50, tbs_tableCsv='ltetbs.csv'):
        
        self.nulrb = nulrb
        self.tbs_table = list()
        directory = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(directory, tbs_tableCsv)
        with open(file_path, 'r', newline='') as tbsfile:
            reader = csv.reader(tbsfile)
            for row in reader:
                self.tbs_table.append([int(tbs) for tbs in row])
                
        self.ul_format_0_grant_table = self.generate_ul_format_0_grant_table()
        self.ul_format_1_grant_table = self.generate_ul_format_1_grant_table()

    def get_ul_format_0_grant(self, riv):
        return self.ul_format_0_grant_table[riv]
        
    def get_ul_format_1_grant(self, alloc):
        return self.ul_format_1_grant_table[alloc]
        
    def get_ul_tbs(self, nrb, tbs_index):
        return self.tbs_table[nrb][tbs_index]

    def get_ul_grant_from_frame_and_subframe(self, frame, subframe):
        absolute_subframe = frame*10 + subframe
        tx_absolute_subframe = (absolute_subframe + 4) % (self.ABSOLUTE_SUBFRAME_MAX+1)
        
        ul_frame = int(math.floor(tx_absolute_subframe/10.0))
        ul_subframe = tx_absolute_subframe - ul_frame*10

        return (ul_frame, ul_subframe)
        
    def set_nulrb(self, nulrb):
        self.ul_format_0_grant_table = self.generate_ul_format_0_grant_table()
        self.ul_format_1_grant_table = self.generate_ul_format_1_grant_table()
        self.nulrb = nulrb
        return True
        
    def nrb_to_p(self,nrb):
        if nrb == 6:
            p = 1
        elif nrb == 15:
            p = 2
        elif nrb == 25:
            p = 2
        elif nrb == 50:
            p = 3
        elif nrb == 75:
            p = 4
        elif nrb == 100:
            p = 4
            
        return p

    def fact(self,n):
        if n == 0 or n == 1:
            return 1
            
        ret = n    
        for i in range(2,n):
            ret = ret * i
        return ret
        
    def binomial_coefficient(self, n,k):
        return self.fact(n)/(self.fact(k)*self.fact(n-k))
            
    def dci_0_format_1_rb_to_r(self,nrb, s0, s1, s2, s3):

        p = self.nrb_to_p(nrb)
            
        n = math.ceil(nrb / p) + 1
        
        x0 = self.binomial_coefficient(n-s0,4)
        x1 = self.binomial_coefficient(n-s1,3)
        x2 = self.binomial_coefficient(n-s2,2)
        x3 = self.binomial_coefficient(n-s3,1)
        
        return int(x0 + x1 + x2 + x3)

    def riv_to_rb(self,riv,nulrb):
        for l_crb in range(1,nulrb+1):
            for rb_start in range(0,nulrb-l_crb+1):
                if (l_crb-1) <= math.floor(nulrb/2):
                    if riv == nulrb*(l_crb-1)+ rb_start:
                        return l_crb, rb_start
                else:
                    if riv == nulrb*(nulrb-l_crb+1) + (nulrb-1-rb_start):
                        return l_crb, rb_start
        return (None,None)

    def is_ul_allocation_valid(self, nrb):
        return ((nrb % 2 == 0) or
                (nrb % 3 == 0) or
                (nrb % 5 == 0) or
                (nrb == 1))
        
    def generate_ul_format_0_grant_table(self):
        riv_table = 9999*[0]
        for riv in range(0,9999):
            l_crb, rb_start = self.riv_to_rb(riv,self.nulrb)
            if l_crb is None:
                riv_table[riv] = (0,0)
            else:
                riv_table[riv] = (l_crb,rb_start)
        return riv_table
        
    def generate_ul_format_1_grant_table(self):
        table = 15000*[None]
        p = self.nrb_to_p(self.nulrb)
        n = math.ceil(self.nulrb / p) + 1
        for s0 in range(1,n-3):
            for s1 in range(s0+1,n-2):
                for s2 in range(s1+1,n-1):
                    for s3 in range(s2+1,n):
                        r = self.dci_0_format_1_rb_to_r(self.nulrb,s0,s1,s2,s3)
                        while r > len(table): 
                            table.append(10*[None])
                        if table[r] is None:
                            #table[r] = (s0, s1, s2, s3)
                    
                            rb_start_0 = s0*p
                            rb_alloc_0 = ((s1-1)-s0)*p
                            
                            rb_start_1 = s2*p
                            rb_end_1 = min(self.nulrb,(s3-1)*p)
                            rb_alloc_1 = rb_end_1 - rb_start_1  
                            
                            table[r] = (rb_start_0, rb_alloc_0, rb_start_1, rb_alloc_1)
                        else:
                            print(f'Error: {r} mapped to {table[r]}:: ({s0},{s1},{s2},{s3}).')
        return table