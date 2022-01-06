# NSX Routing Set
# Developed for SRM v 8.5.0

import http.client
import ssl
import json
import sys
import pickle
import base64
import time


# API Parameters
APIbaseURL = "/policy/api/v1"
sslcheck = ssl._create_unverified_context()


# Persistent Storage Files
# User Store
user_f = "user.p"
# Parameter Store
param_f = "param.p"
# System State Information
state_f = "state.p"


def _buildUSERenv():
    try:
        file = open(user_f, 'rb')
    except OSError:
        print("Base user configuration file not set - specify with setuser")
        sys.exit()
    uspec = pickle.load(file)
    file.close()
    return uspec


def _buildPARAMenv():
    try:
        file = open(param_f, 'rb')
    except OSError:
        print("Base configuration not set - specify with setparams")
        sys.exit()
    pspec = pickle.load(file)
    file.close()
    return pspec


def _buildSTATE():
    try:
        file = open(state_f, 'rb')
    except OSError:
        print("Base configuration not set - specify with setparams")
        sys.exit()
    sspec = pickle.load(file)
    file.close()
    return sspec


def _getHeaders():
    uspec = _buildUSERenv()
    usrpwd_b64t = uspec['b64usrpwd']
    getHeaders = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {usrpwd_b64t}'
    }
    return getHeaders


def getURL(host, url, sslcontext):
    fullurl = APIbaseURL + url
    payload = ''
    headers = _getHeaders()
    conn = http.client.HTTPSConnection(host, context=sslcontext)
    conn.request("GET", fullurl, payload, headers)
    ures = conn.getresponse()
    if not ures.status == 200:
        print('Failed to return - Error: ' + str(ures.status))
        exit()
    udata = ures.read()
    try:
        fdata = json.loads(udata.decode("utf-8"))
    except ValueError:
        print('Cannot Load JSON response - ' + str(udata.decode("utf-8")))
    return fdata


def putURL(host, url, intpayload, sslcontext):
    fullurl = APIbaseURL + url
    conn = http.client.HTTPSConnection(host, context=sslcontext)
    payload = json.dumps(intpayload)
    headers = _getHeaders()
    conn.request("PUT", fullurl, payload, headers)
    res = conn.getresponse()
    data = res.read()
    rs = data.decode("utf-8")
    return rs


def confirmRouters():
    pspec = _buildPARAMenv()
    rspec = dict()
    jdata = getURL(pspec['targethost'], '/infra/tier-1s', sslcheck)
    if jdata['results']:
        for i in jdata['results']:
            if i['display_name'] == pspec['tier1pri_name']:
                rspec['pripath'] = i['path']
            elif i['display_name'] == pspec['tier1dr_name']:
                rspec['drpath'] = i['path']
            else:
                rspec['scriptState'] = False
                rspec['scriptmsg'] = 'Primary or DR not found - Confirm config environment variables'
                return rspec
        rspec['scriptmsg'] = 'Routers Confirmed - Paths Collected'
        rspec['scriptState'] = True
    return rspec


def t1State(rs):
    pspec = _buildPARAMenv()
    if rs['scriptState']:
        prijdata = getURL(pspec['targethost'], rs['pripath'], sslcheck)
        drjdata = getURL(pspec['targethost'], rs['drpath'], sslcheck)
        rs['tier1pri'] = prijdata
        rs['tier1dr'] = drjdata
        rs['scriptState'] = True
        rs['scriptmsg'] = 'States Collected'
    else:
        rs['scriptState'] = False
        rs['scriptmsg'] = 'Failed to get T1 policy state'
    return rs


def drrouteadvcheck():
    rs = confirmRouters()
    rs = t1State(rs)
    stored_state = _buildSTATE()
    if rs['scriptState']:
        if not rs['tier1pri']['route_advertisement_types'] == stored_state['tier1pri']['route_advertisement_types']:
            rs['scriptState'] = False
            rs['scriptmsg'] = 'Error - Pri route states do not match config requirements'
        elif not rs['tier1dr']['route_advertisement_types'] == stored_state['tier1dr']['route_advertisement_types']:
            rs['scriptState'] = False
            rs['scriptmsg'] = 'Error - DR route states do not match config requirements'
        else:
            rs['scriptState'] = True
            rs['scriptmsg'] = 'Config confirmed against stored config - DR Ready for failover'
            print(rs['scriptmsg'])
        return rs
    return rs


def prirouteadvcheck():
    rs = confirmRouters()
    rs = t1State(rs)
    stored_state = _buildSTATE()
    if rs['scriptState']:
       if not rs['tier1dr']['route_advertisement_types'] == stored_state['tier1pri']['route_advertisement_types']:
           rs['scriptState'] = False
           rs['scriptmsg'] = 'Failback Check Error - Pri route states do not match config requirements'
       elif not rs['tier1pri']['route_advertisement_types'] == stored_state['tier1dr']['route_advertisement_types']:
           rs['scriptState'] = False
           rs['scriptmsg'] = 'Failback Check Error - DR route states do not match config requirements'
       else:
           rs['scriptState'] = True
           rs['scriptmsg'] = 'Config confirmed against stored config - DR Ready for failback'
           print(rs['scriptmsg'])
       return rs
    return rs


def setDRroute(rs):
    pspec = _buildPARAMenv()
    if rs['scriptState']:
        rs['old_tier1pri'] = rs['tier1pri']
        rs['old_tier1dr'] = rs['tier1dr']
        payloaddr = {
            '_revision': rs['tier1dr']['_revision'],
            'route_advertisement_types': rs['tier1pri']['route_advertisement_types'],
            'display_name': rs['tier1dr']['display_name']
        }
        payloadpri = {
            '_revision': rs['tier1pri']['_revision'],
            'route_advertisement_types': rs['tier1dr']['route_advertisement_types'],
            'display_name': rs['tier1pri']['display_name']
        }
        drputstate = putURL(pspec['targethost'], rs['drpath'], payloaddr, sslcheck)
        priputstate = putURL(pspec['targethost'], rs['pripath'], payloadpri, sslcheck)
        rs['tier1pri'] = json.loads(priputstate)
        rs['tier1dr'] = json.loads(drputstate)
        rs['scriptState'] = True
        rs['scriptmsg'] = "Config Applied Primary: " + str(payloadpri['route_advertisement_types']) + ' Config Applied DR: ' + str(payloaddr['route_advertisement_types'])
    return rs


def setUSER():
    uspec = dict()
    username = input('Username: ')
    password = input('Password: ')
    usrpwd = username + ":" + password
    usrpwd_b = usrpwd.encode('ascii')
    usrpwd_b64 = base64.b64encode(usrpwd_b)
    uspec['username'] = username
    uspec['b64usrpwd'] = usrpwd_b64.decode('ascii')
    uspec['modified_time'] = time.time()
    try:
        file = open(user_f, 'wb')
    except OSError:
        print('File error cannot set config')
        sys.exit()
    pickle.dump(uspec, file)
    file.close()
    print(uspec)
    return


def setPARAM():
    pspec = dict()
    print('TIER1 device names from NSX console.')
    tier1_pri = input('Primary TIER1: ')
    tier1_dr = input('DR TIER1: ')
    print('NSX Host for API calls')
    nsx_host = input('NSX Host for API: ')
    pspec['tier1pri_name'] = tier1_pri
    pspec['tier1dr_name'] = tier1_dr
    pspec['targethost'] = nsx_host
    pspec['modified_time'] = time.time()
    try:
        file = open(param_f, 'wb')
    except OSError:
        print('File error cannot set config')
        sys.exit()
    pickle.dump(pspec, file)
    file.close()
    print(pspec)
    return


def main(argv):
    if argv[1] == "setuser":
        setUSER()
    elif argv[1] == "setparams":
        setPARAM()
    elif argv[1] == "confirmt1":
        rspec = confirmRouters()
        print(rspec['scriptmsg'])
        print(rspec)
    elif argv[1] == "getrtconf":
        rspec = confirmRouters()
        rspec = t1State(rspec)
        print(rspec['scriptmsg'])
        print(rspec)
        print('\r\nPrimary Route Advertisements Config: ')
        print(rspec['tier1pri']['route_advertisement_types'])
        print('\r\nDR Route Advertisements Config: ')
        print(rspec['tier1dr']['route_advertisement_types'])
    elif argv[1] == "setrtconf":
        rspec = confirmRouters()
        rspec = t1State(rspec)
        print(rspec['scriptmsg'])
        print(rspec)
        print('\r\nPrimary Route Advertisements Config: ')
        print(rspec['tier1pri']['route_advertisement_types'])
        print('\r\nDR Route Advertisements Config: ')
        print(rspec['tier1dr']['route_advertisement_types'])
        rspec['modified_time'] = time.time()
        try:
            file = open(state_f, 'wb')
        except OSError:
            print('File error cannot set config')
            sys.exit()
        pickle.dump(rspec, file)
        file.close()
        print('\r\nConfiguration Stored.')
    elif argv[1] == "checkfailover":
        rspec = drrouteadvcheck()
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['scriptmsg'])
    elif argv[1] == "checkfailback":
        rspec = prirouteadvcheck()
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['scriptmsg'])
    elif argv[1] == "failover":
        rspec = drrouteadvcheck()
        rspec = setDRroute(rspec)
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['scriptmsg'])
    elif argv[1] == "failback":
        rspec = prirouteadvcheck()
        rspec = setDRroute(rspec)
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['scriptmsg'])
    else:
        print('No argument set')


if __name__ == '__main__':
    main(sys.argv)