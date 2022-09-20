# covid19-spectrum-monitoring

Source code, flowgraphs, and related utilities for the COVID-19 distributed spectrum monitoring project.

##### Hardware care during use
* Try to keep the SDR plugged into USB on your computer as much as possible. This provides grounding that reduces the risk of damage from static shock.
* Try to keep wireless devices like your laptop and phone at least about 0.5m (~1.5 ft) away from the SDR.

##### Other tools
* `scripts/run jupyter notebook server.bat`

  If you have an Anaconda python 3.x distribution installed, this starts a jupyterlab server here
  for doing analysis with notebooks

* `grc/bladeRF2_front_panel.grc`

  Acquire samples from the SDR and show their real time spectrum on a virtual front-panel