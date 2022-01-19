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
# Connection Timeout for NSX  x10 sec
conn_timeout = 100
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
    get_headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {usrpwd_b64t}'
    }
    return get_headers


def getURL(url, sslcontext):
    global ures, fdata
    uspec = _buildUSERenv()
    fullurl = APIbaseURL + url
    payload = ''
    headers = _getHeaders()
    constatus = 0
    j = 0
    while constatus != 200 and j < conn_timeout:
        conn = http.client.HTTPSConnection(uspec['targethost'], context=sslcontext, timeout=10)
        try:
            conn.request("GET", fullurl, payload, headers)
        except OSError:
            pass
        try:
            ures = conn.getresponse()
            constatus = ures.status
        except (OSError, AttributeError):
            constatus = 0
        j = j + 1
        if constatus == 503:
            time.sleep(10)
    if constatus == 0:
        print('Connection Time Out')
        sys.exit()
    udata = ures.read()
    try:
        fdata = json.loads(udata.decode("utf-8"))
    except ValueError:
        print('Cannot Load JSON response - ' + str(udata.decode("utf-8")))
    return fdata


def putURL(url, intpayload, sslcontext):
    uspec = _buildUSERenv()
    fullurl = APIbaseURL + url
    conn = http.client.HTTPSConnection(uspec['targethost'], context=sslcontext)
    payload = json.dumps(intpayload)
    headers = _getHeaders()
    conn.request("PUT", fullurl, payload, headers)
    res = conn.getresponse()
    data = res.read()
    rs = data.decode("utf-8")
    return rs


def getTier1():
    rspec = dict()
    jdata = getURL('/infra/tier-1s', sslcheck)

    print('Tier 1 ID                           \tDisplay Name')
    print('------------------------------------\t----------------------------------------------')
    if jdata['results']:
        for i in jdata['results']:
            print(str(i['unique_id']) + '\t' + str(i['display_name']))
        rspec['scriptmsg'] = 'Tier1 Routers - Listed'
        rspec['scriptState'] = True
    print('------------------------------------\t----------------------------------------------')
    print('\n')
    return rspec


def confirmRouters():
    pspec = _buildPARAMenv()
    rspec = dict()
    jdata = getURL('/infra/tier-1s', sslcheck)
    if jdata['results']:
        for i in jdata['results']:
            if i['unique_id'] == pspec['tier1pri_id']:
                rspec['pripath'] = i['path']
            elif i['unique_id'] == pspec['tier1dr_id']:
                rspec['drpath'] = i['path']
        try:
            rspec['pripath']
        except KeyError:
            rspec['scriptmsg'] = 'Primary T1 Not Found - Check Parameters'
            rspec['scriptState'] = False
            return rspec
        try:
            rspec['drpath']
        except KeyError:
            rspec['scriptmsg'] = 'DR T1 Not Found - Check Parameters'
            rspec['scriptState'] = False
            return rspec
        rspec['scriptmsg'] = 'Routers Confirmed - Paths Collected'
        rspec['scriptState'] = True
    return rspec


def t1State(rs):
    if rs['scriptState']:
        prijdata = getURL(rs['pripath'], sslcheck)
        drjdata = getURL(rs['drpath'], sslcheck)
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
            rs['exMsg'] = "*** Executing Primary --> DR configuration ***"
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
            rs['exMsg'] = "*** Executing DR --> Primary configuration ***"
            rs['scriptmsg'] = 'Config confirmed against stored config - DR Ready for failback'
            print(rs['scriptmsg'])
        return rs


def execute():
    rs = dict()
    prirs = prirouteadvcheck()
    drrs = drrouteadvcheck()

    if drrs['scriptState']:
        rs = setDRroute(drrs)
    elif prirs['scriptState']:
        rs = setDRroute(prirs)
    else:
        rs['scriptState'] = False
        rs['exMsg'] = "Nothing Changed"
        rs['scriptmsg'] = 'Something is Wrong'
    return rs


def setDRroute(rs):
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
        drputstate = putURL(rs['drpath'], payloaddr, sslcheck)
        priputstate = putURL(rs['pripath'], payloadpri, sslcheck)
        rs['tier1pri'] = json.loads(priputstate)
        rs['tier1dr'] = json.loads(drputstate)
        rs['scriptState'] = True
        rs['scriptmsg'] = "Config Applied Primary: " + str(payloadpri['route_advertisement_types']) + \
                          ' Config Applied DR: ' + str(payloaddr['route_advertisement_types'])
    return rs


def setUSER():
    uspec = dict()
    username = input('Username: ')
    password = input('Password: ')
    api_host = input('API Host (NSX Manager): ')
    usrpwd = username + ":" + password
    usrpwd_b = usrpwd.encode('ascii')
    usrpwd_b64 = base64.b64encode(usrpwd_b)
    uspec['username'] = username
    uspec['b64usrpwd'] = usrpwd_b64.decode('ascii')
    uspec['targethost'] = api_host
    uspec['modified_time'] = time.time()
    try:
        file = open(user_f, 'wb')
    except OSError:
        print('File error cannot set config')
        sys.exit()
    pickle.dump(uspec, file)
    file.close()
    print('\n')
    print(uspec)
    return


def setPARAM():
    pspec = dict()
    getTier1()
    print('Choose the ID from above:')
    tier1_pri_id = input('Primary ID TIER1: ')
    tier1_dr_id = input('DR ID TIER1: ')
    pspec['tier1pri_id'] = tier1_pri_id
    pspec['tier1dr_id'] = tier1_dr_id
    pspec['modified_time'] = time.time()
    try:
        file = open(param_f, 'wb')
    except OSError:
        print('File error cannot set config')
        sys.exit()
    pickle.dump(pspec, file)
    file.close()
    print('\n')
    print(pspec)
    return


def main(argv):
    if argv[1] == "setuser":
        setUSER()
    elif argv[1] == "setparams":
        setPARAM()
    elif argv[1] == "gettier1":
        rspec = getTier1()
        json_d = json.dumps(rspec)
        logger.debug(json_d)
        print(rspec['scriptmsg'])
        print(rspec)
    elif argv[1] == "confirmt1":
        rspec = confirmRouters()
        print('\n')
        print(rspec['scriptmsg'])
        print('\n')
        print(rspec)
        logger.debug(str(rspec))
    elif argv[1] == "getrtconf":
        rspec = confirmRouters()
        rspec = t1State(rspec)
        print(rspec['scriptmsg'])
        print(rspec)
        print('\r\nPrimary Route Advertisements Config: ')
        print(rspec['tier1pri']['route_advertisement_types'])
        print('\r\nDR Route Advertisements Config: ')
        print(rspec['tier1dr']['route_advertisement_types'])
        logger.debug(str(rspec))
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
        print(rspec['exMsg'])
        print('\r\n')
        print(rspec['scriptmsg'])
    elif argv[1] == "failback":
        rspec = prirouteadvcheck()
        rspec = setDRroute(rspec)
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['exMsg'])
        print('\r\n')
        print(rspec['scriptmsg'])
    elif argv[1] == "execute":
        rspec = execute()
        print('\r\n')
        print(rspec)
        print('\r\n')
        print(rspec['exMsg'])
        print('\r\n')
        print(rspec['scriptmsg'])
    else:
        print('No argument set')


if __name__ == '__main__':
    main(sys.argv)
