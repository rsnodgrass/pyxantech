The goal of the protocol YAML files was to provide an easy to parse standard format for describing the features
and protocol of matrix audio switches/amplifiers. YAML is easily dynamically converted into JSON (or XML), but
much easier to read. These protocol YAML files could be used by other non-Python based libraries building
similar functionality.

NOTE: Other matrix multi-zone amplifier brands/models can be added, though ones that are HEX based protocols are probably
not ideal for this type of regexp remapping. That includes Parasound, HTL, Russound, Knox, B&K, AudioControl and others.
With some tweaks, pyxantech may be able to start supporting HEX based protocols, which would be great to open the door
to a wide variety of legacy/current matrix amps.

Proprietary amps like Crestron and RTi are probably outside the realm of a mapping solution like what is provided by pyxantech.

This metadata format and pyxantech could possibly be extended to support VIDEO matrix as well as audio.


