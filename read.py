# routines for reading spectrum monitoring data files

import numpy as np
import pandas as pd
import os.path
import yaml

def yaml_metadata(data_path):
    entries = os.path.split(data_path)
    name = os.path.splitext(entries[-1])[0].rsplit('.',1)[0]+'.yaml'
    yaml_path = os.path.join(*(entries[:-1]+(name,)))
    with open(yaml_path, 'rb') as f:
        metadata = yaml.load(f, Loader=yaml.SafeLoader)

    metadata['center_frequencies'] = sorted([k for k in metadata.keys() if isinstance(k,float)])
    return metadata

def _assert_version(expected, actual):
    if actual != expected:
        raise ValueError('expected file format code %i., but given %f'%(expected, actual))    

def swept_average_merge(src_path, dest_path):
    # pull in metadata
    src_metadata = yaml_metadata(src_path)
    dest_metadata = yaml_metadata(dest_path)

    dwell_samples = int(src_metadata['dwell_time']/src_metadata['aperture_time'])
    dwell_count = len(src_metadata['center_frequencies'])
    field_count = 5+dwell_samples
    sweep_fields = field_count*dwell_count   
    
    entries = os.path.split(src_path)
    name = os.path.splitext(entries[-1])[0].rsplit('.',1)[0]+'.yaml'
    yaml_path = os.path.join(*(entries[:-1]+(name,)))      
    
    # validate metadata
    missing = set(dest_metadata.keys()).difference(src_metadata.keys())
    if len(missing)>0:
        raise KeyError('dest file is missing metadata keys %s'%str(missing))
    mismatched = {k for k in dest_metadata.keys() if src_metadata[k] != dest_metadata[k]}
    if len(mismatched)>0:
        raise ValueError('dest file metadata mismatched for keys %s'%str(mismatched))
          
    src = np.fromfile(src_path, dtype='float32')
    dest = np.fromfile(dest_path, dtype='float32')
    
    if src.size > 0 and src[0] != -4:
        raise ValueError("both file versions must be 4, but source is v%i"%(-src[0]))

    if dest.size > 0:
        if dest[0] > -4:
             raise ValueError("both file versions must be 4, but destination version is v%i"%(-dest[0]))

        # truncate dest to an integer number of sweeps
        dest = dest[:(dest.shape[0]//sweep_fields)*sweep_fields]
                         
    # merge the data and write
    merged = np.append(dest, src)
    merged.tofile(dest_path)
    os.remove(src_path)
    os.remove(yaml_path)
        
def _swept_average_v4(path, holdoff=0.05, dwell_settle=0, calibrate=True):
    metadata = yaml_metadata(path)
    dwell_time = metadata['dwell_time']
    aperture_time = metadata['aperture_time']   
    center_frequencies = metadata['center_frequencies']
    
    
    dwell_samples=int(round(dwell_time/aperture_time))
    
    raw = np.fromfile(path, dtype='float32')
    _assert_version(-4, raw[0])
    metadata['version'] = -4
    
    print('reading v4 data file')

    # each dwell window consists of (version_tag, frequency, dwell_window_sample_peak,)
    # then the sequence of dwell_samples samples of average power
    field_count = 5+dwell_samples

    # truncate to an integer number of dwell windows
    raw = raw[:(raw.size//field_count)*(field_count)]

    spectrum = pd.DataFrame(raw.reshape(raw.size//field_count,field_count))
    spectrum.columns = ['Version', 'Time01', 'Time23', 'Frequency', 'Sample peak'] + list(range(dwell_samples))
    
    # cast each pair of 32-bit time fields into a single 64-bit time 
    time_fields = raw.reshape((raw.size//field_count,field_count))[:,1:3]
    spectrum['Time'] = np.frombuffer(time_fields.tobytes(), dtype='float64')
    spectrum = spectrum.drop(['Time01', 'Time23'],axis=1)
    del raw
    
    spectrum = spectrum.drop('Version', axis=1)
    spectrum['Frequency'] = np.round(spectrum['Frequency']/1e6*10)/10
    spectrum['Time'] = pd.to_datetime(spectrum['Time'], unit='s', utc=True)
    spectrum['Time'] = pd.DatetimeIndex(spectrum['Time']).tz_convert('America/Denver')
    spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
    spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
    frequency_count = len(center_frequencies)

    # spectrum.Time = dwell_time*frequency_count*np.floor(spectrum.Time/frequency_count)
    # spectrum.Frequency /= 1e6
    # spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10 # round to nearest 1 kHz
#     spectrum = spectrum.set_index(['Time', 'Frequency'])

    # move the sample peaks to metadata, and out of spectrum
    metadata['peak_sample'] = spectrum.loc[:,:'Sample peak'].iloc[:,-1:] # 'Sample Peak' as a DataFrame, not Series
    spectrum = spectrum.drop('Sample peak', axis=1)

    # Ettus USRPs output 0 as an "invalid" sentinel
    # spectrum = spectrum.replace(0,np.nan)
    
    # Assign a sweep and set the indices
#     spectrum = spectrum.reset_index()
    
    
    spectrum.columns.name = 'Dwell time elapsed (s)'
    spectrum.columns = spectrum.columns.astype('float') * metadata['aperture_time']
    
    # the actual hardware synchronization is loose. invalid and nan values may intermittently
    # continue for up to a couple hundred ms on some SDRs. this fills in everything through
    # the final nan value with nan. later code will interpret this data to ignore.
    throwaway = int(round(holdoff/aperture_time))
    correction = np.cumsum(spectrum.shift(throwaway, axis=1).values[:,::-1],axis=1)[:,::-1]*0
    spectrum.values[:] += correction
    spectrum.values[:,:dwell_settle] = np.nan
    spectrum = spectrum.dropna(axis=1, how='all')
    
    # apply the calibration data
    if calibrate:
        for fc in spectrum.index.levels[2]:
            idx = spectrum.index.get_level_values(2) == fc
            fc_lookup = (np.round(fc*10)/10.)*1e6
            spectrum.values[idx] += -metadata[fc_lookup]['noise_average']
            spectrum.values[idx] *= metadata[fc_lookup]['power_correction']

#     # repeat this, because bizarrely there is rounding error otherwise
#     spectrum = spectrum.reset_index()
#     spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10
#     spectrum['Time'] = pd.Timestamp.fromtimestamp(spectrum['Time'])
#     spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
#     spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
#     spectrum.columns.name = 'Aperture power sample'
    
    return spectrum, metadata
        
def _swept_average_v3(path, holdoff=0.05, dwell_settle=0, calibrate=True):
    metadata = yaml_metadata(path)
    dwell_time = metadata['dwell_time']
    aperture_time = metadata['aperture_time']   
    center_frequencies = metadata['center_frequencies']
    
    
    dwell_samples=int(round(dwell_time/aperture_time))
    
    raw = np.fromfile(path, dtype='float32')
    _assert_version(-3, raw[0])
    metadata['version'] = -3
    
    print('reading v3 data file')

    # each dwell window consists of (version_tag, frequency, dwell_window_sample_peak,)
    # then the sequence of dwell_samples samples of average power
    field_count = 4+dwell_samples

    # truncate to an integer number of dwell windows
    raw = raw[:(raw.size//field_count)*(field_count)]

    spectrum = pd.DataFrame(raw.reshape(raw.size//field_count,field_count))
    del raw
    spectrum.columns = ['Version', 'Time', 'Frequency', 'Sample peak'] + list(range(dwell_samples))
    spectrum = spectrum.drop('Version', axis=1)
    spectrum['Frequency'] = np.round(spectrum['Frequency']/1e6*10)/10
    spectrum['Time'] = pd.to_datetime(spectrum['Time'], unit='s', utc=True)
    spectrum['Time'] = pd.DatetimeIndex(spectrum['Time']).tz_convert('America/Denver')
    spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
    spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
    frequency_count = len(center_frequencies)

    # spectrum.Time = dwell_time*frequency_count*np.floor(spectrum.Time/frequency_count)
    # spectrum.Frequency /= 1e6
    # spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10 # round to nearest 1 kHz
#     spectrum = spectrum.set_index(['Time', 'Frequency'])

    # move the sample peaks to metadata, and out of spectrum
    metadata['peak_sample'] = spectrum.loc[:,:'Sample peak'].iloc[:,-1:] # 'Sample Peak' as a DataFrame, not Series
    spectrum = spectrum.drop('Sample peak', axis=1)

    # Ettus USRPs output 0 as an "invalid" sentinel
    # spectrum = spectrum.replace(0,np.nan)
    
    # Assign a sweep and set the indices
#     spectrum = spectrum.reset_index()
    
    
    spectrum.columns.name = 'Dwell time elapsed (s)'
    spectrum.columns = spectrum.columns.astype('float') * metadata['aperture_time']
    
    # the actual hardware synchronization is loose. invalid and nan values may intermittently
    # continue for up to a couple hundred ms on some SDRs. this fills in everything through
    # the final nan value with nan. later code will interpret this data to ignore.
    throwaway = int(round(holdoff/aperture_time))
    correction = np.cumsum(spectrum.shift(throwaway, axis=1).values[:,::-1],axis=1)[:,::-1]*0
    spectrum.values[:] += correction
    spectrum.values[:,:dwell_settle] = np.nan
    spectrum = spectrum.dropna(axis=1, how='all')
    
    # apply the calibration data
    if calibrate:
        for fc in spectrum.index.levels[2]:
            idx = spectrum.index.get_level_values(2) == fc
            fc_lookup = (np.round(fc*10)/10.)*1e6
            spectrum.values[idx] += -metadata[fc_lookup]['noise_average']
            spectrum.values[idx] *= metadata[fc_lookup]['power_correction']

#     # repeat this, because bizarrely there is rounding error otherwise
#     spectrum = spectrum.reset_index()
#     spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10
#     spectrum['Time'] = pd.Timestamp.fromtimestamp(spectrum['Time'])
#     spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
#     spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
#     spectrum.columns.name = 'Aperture power sample'
    
    return spectrum, metadata
        
def _swept_average_v2(path, holdoff=0.05, dwell_settle=0):   
    metadata = yaml_metadata(path)
    dwell_time = metadata['dwell_time']
    aperture_time = metadata['aperture_time']   
    center_frequencies = metadata['center_frequencies']
    dwell_samples=int(round(dwell_time/aperture_time))
    print(dwell_time, aperture_time, dwell_samples)
    
    raw = np.fromfile(path, dtype='float32')
    _assert_version(-2, raw[0])
    metadata['version'] = -2

    # each dwell window consists of (version_tag, frequency, dwell_window_sample_peak,)
    # then the sequence of dwell_samples samples of average power
    field_count = 4+dwell_samples

    # truncate to an integer number of dwell windows
    raw = raw[:(raw.size//field_count)*(field_count)]

    spectrum = pd.DataFrame(raw.reshape(raw.size//field_count,field_count))
    del raw
    spectrum.columns = ['Version', 'Time', 'Frequency', 'Sample peak'] + list(range(dwell_samples))
    spectrum = spectrum.drop('Version', axis=1)
    spectrum['Frequency'] = np.round(spectrum['Frequency']/1e6*10)/10
    spectrum['Time'] = pd.to_datetime(spectrum['Time'], unit='s', utc=True)
    spectrum['Time'] = pd.DatetimeIndex(spectrum['Time']).tz_convert('America/Denver')
    spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
    spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
    frequency_count = len(center_frequencies)

    # spectrum.Time = dwell_time*frequency_count*np.floor(spectrum.Time/frequency_count)
    # spectrum.Frequency /= 1e6
    # spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10 # round to nearest 1 kHz
#     spectrum = spectrum.set_index(['Time', 'Frequency'])

    # move the sample peaks to metadata, and out of spectrum
    metadata['peak_sample'] = spectrum.loc[:,:'Sample peak'].iloc[:,-1:] # 'Sample Peak' as a DataFrame, not Series
    spectrum = spectrum.drop('Sample peak', axis=1)

    # Ettus USRPs output 0 as an "invalid" sentinel
    # spectrum = spectrum.replace(0,np.nan)
    
    # Assign a sweep and set the indices
#     spectrum = spectrum.reset_index()
    
    
    spectrum.columns.name = 'Dwell time elapsed (s)'
    spectrum.columns = spectrum.columns.astype('float') * metadata['aperture_time']
    
    # the actual hardware synchronization is loose. invalid and nan values may intermittently
    # continue for up to a couple hundred ms on some SDRs. this fills in everything through
    # the final nan value with nan. later code will interpret this data to ignore.
    throwaway = int(round(holdoff/aperture_time))
    correction = np.cumsum(spectrum.shift(throwaway, axis=1).values[:,::-1],axis=1)[:,::-1]*0
    spectrum.values[:] += correction
    spectrum.values[:,:dwell_settle] = np.nan
    spectrum = spectrum.dropna(axis=1, how='all')

#     # repeat this, because bizarrely there is rounding error otherwise
#     spectrum = spectrum.reset_index()
#     spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10
#     spectrum['Time'] = pd.Timestamp.fromtimestamp(spectrum['Time'])
#     spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
#     spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
#     spectrum.columns.name = 'Aperture power sample'
    
    return spectrum, metadata

def _swept_average_v1(path, holdoff=0.325, dwell_settle=0):   
    metadata = yaml_metadata(path)
    dwell_time = metadata['dwell_time']
    aperture_time = metadata['aperture_time']   
    center_frequencies = metadata['center_frequencies']
    dwell_samples=int(round(dwell_time/aperture_time))
    
    raw = np.fromfile(path, dtype='float32')
    _assert_version(-1, raw[0])
    metadata['version'] = -1

    # each dwell window consists of (version_tag, frequency, dwell_window_sample_peak,)
    # then the sequence of dwell_samples samples of average power
    field_count = 3+dwell_samples

    # truncate to an integer number of dwell windows
    raw = raw[:(raw.size//field_count)*(field_count)]

    spectrum = pd.DataFrame(raw.reshape(raw.size//field_count,field_count)).reset_index()
    del raw
    spectrum.columns = ['Time', 'Version', 'Frequency', 'Sample peak'] + list(range(dwell_samples))
    spectrum['Frequency'] = np.round(spectrum['Frequency']/1e6*10)/10
    frequency_count = spectrum.Frequency.unique().size

    # spectrum.Time = dwell_time*frequency_count*np.floor(spectrum.Time/frequency_count)
    # spectrum.Frequency /= 1e6
    # spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10 # round to nearest 1 kHz
    spectrum = spectrum.set_index(['Time', 'Frequency'])

    # move the sample peaks to metadata, and remove it from spectrum
    metadata['peak_sample'], spectrum = spectrum.iloc[:,1:2], spectrum.iloc[:,2:]
    metadata['peak_sample'] = metadata['peak_sample'].reset_index().set_index('Time')

    # Ettus USRPs output 0 as an "invalid" sentinel
    # spectrum = spectrum.replace(0,np.nan)


    # the actual hardware synchronization is loose. invalid and nan values may intermittently
    # continue for up to a couple hundred ms. this fills in everything through the final
    # nan value with nan. later code will interpret this data to ignore.
    throwaway = int(round(holdoff/aperture_time))
    correction = np.cumsum(spectrum.shift(throwaway, axis=1).values[:,::-1],axis=1)[:,::-1]*0
    spectrum.values[:] += correction
    spectrum.values[:,:dwell_settle] = np.nan
    spectrum = spectrum.dropna(axis=1, how='all')

    # repeat this, because bizarrely there is rounding error otherwise
    spectrum = spectrum.reset_index()
    spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10
    spectrum['Time'] = pd.Timestamp.fromtimestamp(metadata['start_timestamp']) + pd.to_timedelta(spectrum.Time, unit='s')
    spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
    spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
    spectrum.columns.name = 'Aperture power sample'
    
    return spectrum, metadata

def _swept_average_v0(path, holdoff=0.18, dwell_settle=0):
    metadata = yaml_metadata(path)
    dwell_time = metadata['dwell_time']
    aperture_time = metadata['aperture_time']   
    center_frequencies = metadata['center_frequencies']
    dwell_samples=int(round(dwell_time/aperture_time))
    
    raw = np.fromfile(path, dtype='float32')
    raw = raw[:(raw.size//(dwell_samples))*dwell_samples]

    global spectrum # for debug
    spectrum = pd.DataFrame(raw.reshape(raw.size//dwell_samples,dwell_samples)).reset_index()
    del raw
    spectrum.columns = ['Time']+list(np.arange(dwell_samples))
    frequency_count = len(center_frequencies)#spectrum.Frequency.unique().size

    spectrum['Time'] = dwell_time*frequency_count*np.floor(spectrum.Time/frequency_count)

    spectrum['Frequency'] = (list(center_frequencies)*int(np.ceil(spectrum.shape[0]/len(center_frequencies))))[:spectrum.shape[0]]
    spectrum.Frequency /= 1e6
    spectrum.loc[:,'Frequency'] = np.round(spectrum.loc[:,'Frequency']*10)/10. # round to nearest 1 kHz
    spectrum = spectrum.set_index(['Time', 'Frequency'])

    # Ettus USRPs output 0 as an "invalid" sentinel
    spectrum = spectrum.replace(0,np.nan) # specific to Ettus USRPs? They seem to give '0' until 

    # the actual hardware synchronization is loose. invalid and nan values may intermittently
    # continue for up to a couple hundred ms. this fills in everything through the final
    # nan value with nan. later code will interpret this data to ignore.
    throwaway = int(round(holdoff/aperture_time))
    correction = np.cumsum(spectrum.shift(throwaway, axis=1).values[:,::-1],axis=1)[:,::-1]*0
    spectrum.values[:] += correction
    spectrum.values[:,:dwell_settle] = np.nan

    spectrum = spectrum.reset_index()
    spectrum['Frequency'] = np.round(spectrum['Frequency']*10)/10
    spectrum['Time'] = pd.Timestamp.fromtimestamp(metadata['start_timestamp']) + pd.to_timedelta(spectrum.Time, unit='s')
    spectrum['Sweep'] = np.floor(np.arange(spectrum.shape[0])/len(center_frequencies)).astype(int)
    spectrum = spectrum.set_index(['Sweep', 'Time', 'Frequency'])
    spectrum.columns.name = 'Aperture power sample'
    
    return spectrum, metadata

def swept_average(path, holdoff=None, dwell_settle=0, **kws):
    version = -np.fromfile(path, dtype='float32', count=1)[0]
    
    kws = dict(kws, path=path, holdoff=holdoff, dwell_settle=dwell_settle)
    if holdoff is None:
        kws.pop('holdoff')

    if version <= 0:
        return _swept_average_v0(**kws)
    
    elif version == 1:
        return _swept_average_v1(**kws)
        
    elif version == 2:
        return _swept_average_v2(**kws)

    elif version == 3:
        return _swept_average_v3(**kws)
    
    elif version == 4:
        return _swept_average_v4(**kws)

    else:
        raise ValueError('data file reports unsupported version number "%f"'%version)