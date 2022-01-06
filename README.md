# NSX SRM - T1 Failover Script

NSX API Script to perform a T1 route change for DR using SRM

### Installation:
- Copy script to SRM appliance.  Follow [VMWare SRM Documentation](https://docs.vmware.com/en/Site-Recovery-Manager/8.5/com.vmware.srm.admin.doc/GUID-4F084B4F-DE9C-4A76-8AD2-19F4A76E81A3.html)

### Operation:
Script arguments:
- `setuser` - Sets up user for API.  Must be configured in NSX
- `setparams` - Sets up parameters for failover operation.
  - `"Primary TIER1"` - Primary Tier 1 Router - name from NSX GUI 
  - `"DR TIER1"` - DR Tier 1 Router - name from NSX GUI
  - `"NSX Host"` - Host Address for API calls 
- `confirmt1` - Confirms the T1 routers defined in the parameters
- `getrtconf` - Gets the current routing config from the T1 devices
- `setrtconf` - Sets the routing config to be used in failover process
- `checkfailover` - Checks the configurations match the stored configs in the "Production" state
- `checkfailback` - Checks the configuration matches the stored states in the "Failover" state
- `failover` - Moves the routing config from Primary to DR - checks config before operation
- `failback` - Moves the routing config from DR to Primary - checks config before operation


#### Notes:
- setuser and setparams must be run before use.
- User parameters are stored on the SRM device and must be changed if NSX changes

Example SRM config for failover:

`/bin/python3 /user/admin/nsxt1srm.py failover`


