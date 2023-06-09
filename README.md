# charging_sites
Identifies groups of EV charging stations in OSM

Dependency: [gml2osm](https://github.com/NKAmapper/gml2osm).

To execute: <code>python charging_sites.py [--noload]</code>

The <code>--noload</code> argument will load OSM charging stations from last saved file instead of loading from Overpass.

A file with all charging stations in OSM will be created. Identified group of charges are indicated with a <code>GROUP=*</code> tag containing the number of potential charge points in the group, and the identified charge points in the group will get a <code>man_made=charge_point</code> tag.

Link to generated [OSM file](https://drive.google.com/file/d/19pBT9zDDIVWt8Eu0gSXXc15BRQLtrknL/view?usp=share_link).
