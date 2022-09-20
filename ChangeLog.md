# ChangeLog

## [2020-06-11]
### Changed
- new finish-environment-setup.py to replace the .bat file; doesn't continue when failures occur, and doesn't depend on user interaction based on buried print messages

## [2020-06-05]
### Changed
- bladeRF watchdog thread now also terminates if there is no activity for at least 30 seconds

## [2020-06-04]
### Changed
- new v4 format with support for the required 64 bits per timestamp

## [2020-06-02]
### Changed
- corrected a timing bug in the dwell acquisition
- new v3 format now saves uncalibrated calibrated (but cal data can be applied after the fact)
- randomization support in the data acquisition
- dramatically reduced dead time between frequencies
- streamlined environment setup
- 

## [2020-05-26]
### Changed
- a watchdog in the bladeRF source now quits on libbladeRF error messages

## [2020-05-19]
### Added
- This ChangeLog.md

### Changed
- increased dwell time in config.yaml to 0.75s, to accommodate the increased frequency-change transition time
- average power data files now have the file name '.swept_power.dat'
- bug fixed: inconsistent noise floor level problems when the OsmoSDR 'CH1' frequency parameter was set to the 'frequency'; now set to constant 100 MHz
- dramatic cleanup in the flowgraphs with virtual sinks to minimize spaghetti