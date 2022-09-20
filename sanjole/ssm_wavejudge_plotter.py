# python 3

import csv
import matplotlib.pyplot as plt
from argparse import ArgumentParser

axes = {'time' : 'Time (s)',
        'users' : 'Users',
        'rbs' : 'RBs',
        'txbits' : 'TX Bits',
        'mcs' : 'Average MCS',
        'alloc' : 'Resource Allocation'}

if __name__ == '__main__':
    # Parse input arguments
    parser = ArgumentParser(description="Plot SanJole wavejudge data from processed CSV file. Made for SSM at NIST.")
    parser.add_argument("-f", "--file", type=str,
                        help="File containing data")
    parser.add_argument("-x", "--xaxis", type=str, default='time',
                        help="What goes on the x-axis (can be time, users, rbs, txbits, mcs, alloc)")
    parser.add_argument('-y', '--yaxis', type=str,
                        help='What goes on the y-axis (can be time, users, rbs, txbits, mcs, alloc)')
    
    args = parser.parse_args()
    
    if not args.file:
        print('Please specify file.')
        sys.exit(1)
    
    if not args.yaxis:
        print('Please specify y-axis.')
        sys.exit(1)
    
    args.xaxis = args.xaxis.lower()
    args.yaxis = args.yaxis.lower()
    
    strFlag = False
    
    X = []
    Y = []
    with open(args.file, 'r') as file_in:
        data = csv.DictReader(file_in)
        for row in data:
            if strFlag or ((args.xaxis == 'time' or args.yaxis == 'time') and not row[axes['time']].find(':') == -1):
                strFlag = True
                timeSplit = row[axes['time']].split(':')
                if args.xaxis == 'time':
                    x = int(timeSplit[0])*3600 + int(timeSplit[1])*60 + float(timeSplit[2])
                    y = float(row[axes[args.yaxis]])
                else:
                    x = float(row[axes[args.xaxis]])
                    y = int(timeSplit[0])*3600 + int(timeSplit[1])*60 + float(timeSplit[2])
            else:
                x = float(row[axes[args.xaxis]])
                y = float(row[axes[args.yaxis]])
            
            X.append(x)
            Y.append(y)
    
    plt.figure()
    plt.plot(X, Y)
    plt.xlabel(axes[args.xaxis])
    plt.ylabel(axes[args.yaxis])
    plt.title(f'{axes[args.yaxis]} vs. {axes[args.xaxis]}')
    plt.show()