from flask import Flask, jsonify, request, abort
from flask_cors import CORS, cross_origin
from network import UCSNet
from server import UCSServer
from session import UCSSession
from util import UCSUtil
from iso import IsoMaker
from db import YamlDB
from autoinstall import Builder

app = Flask(__name__)
CORS(app)

KUBAM_CFG="/kubam/kubam.yaml"
API_ROOT="/api/v1"

@app.route('/')
@cross_origin()
def index():
    return jsonify({'status': 'ok'})


# determine if we have credentials stored or not. 
@app.route(API_ROOT + "/session", methods=['GET'])
@cross_origin()
def get_creds():
    creds = {}
    err, msg, config = YamlDB.open_config(KUBAM_CFG)
    if err == 0:
        if "ucsm" in config and "credentials" in config["ucsm"]:
            creds = config["ucsm"]["credentials"]
            if "user" in creds and "password" in creds and "ip" in creds:
                creds["password"] = "REDACTED"
                #app.logger.info(creds)
    return jsonify({'credentials': creds}), 200


# test with: curl -H "Content-Type: application/json" -X POST -d '{"credentials": {"user" : "admin", "password" : "cisco123", "server" : "172.28.225.163"}}' http://localhost/api/v1/session
# every call logs in and logs out. 
@app.route(API_ROOT + "/session", methods=['POST'])
@cross_origin()
def create_creds():
    if not request.json:
        return jsonify({'error': 'expected credentials hash'}), 400
     
    credentials = {} 
    credentials['user'] = request.json['credentials']['user']
    credentials['password'] = request.json['credentials']['password']
    credentials['ip'] = request.json['credentials']['server']
    if credentials['ip'] == "":
        return jsonify({'error': "Please enter a valid UCSM IP address."}), 401
    #app.logger.info("starting login attempt to UCS.")
    h, err = UCSSession.login(credentials['user'], 
                              credentials['password'],
                              credentials['ip'])
    if h == "":
        return jsonify({'error': err}), 401
    # write datafile. 
    YamlDB.update_ucs_creds(KUBAM_CFG, credentials)
    UCSSession.logout(h)
    return jsonify({'login': "success"}), 201

@app.route(API_ROOT + "/session", methods=['DELETE'])
@cross_origin()
def delete_session():
    YamlDB.update_ucs_creds(KUBAM_CFG, "")
    return jsonify({'logout': "success"})

def not_logged_in(msg):
    if msg == "":
        msg = "not logged in to UCS"
    return jsonify({'error': msg}), 401

# returns err, msg, handle
def login():
    err, msg, config = YamlDB.open_config(KUBAM_CFG)
    if err == 0:
        if "ucsm" in config and "credentials" in config["ucsm"]:
            creds = config["ucsm"]["credentials"]
            if "user" in creds and "password" in creds and "ip" in creds:
                h, msg = UCSSession.login(creds["user"], creds["password"], creds["ip"])
                if h != "":
                    return 0, "", h
                return 1, msg, ""
            else: 
                msg = "kubam.yaml file does not include the user, password, and ip properties to login."
                err = 1
        else:
            msg = "UCS Credentials have not been entered.  Please login to UCS to continue."
            err = 1
    return err, msg, ""
        
def logout(handle):
    UCSSession.logout(handle) 

#get the kubam ip address
@app.route(API_ROOT + "/ip", methods=['GET'])
@cross_origin()
def get_kubam_ip():
    err, msg, ip = YamlDB.get_kubam_ip(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'kubam_ip' : ip}), 200

#update the kubam IP address
@app.route(API_ROOT + "/ip", methods=['POST'])
@cross_origin()
def update_kubam_ip():
    if not request.json:
        return jsonify({'error': 'expected request with kubam_ip '}), 400
    if "kubam_ip" not in request.json:
        return jsonify({'error': 'expected request with kubam_ip '}), 400

    ip = request.json['kubam_ip']
    err, msg = YamlDB.update_kubam_ip(KUBAM_CFG, ip)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'kubam_ip' : ip}), 201

# get the proxy
@app.route(API_ROOT + "/proxy", methods=['GET'])
@cross_origin()
def get_proxy():
    err, msg, keys = YamlDB.get_proxy(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'proxy' : keys}), 200


# update proxy
@app.route(API_ROOT + "/proxy", methods=['POST'])
@cross_origin()
def update_proxy():
    if not request.json:
        return jsonify({'error': 'expected request with proxy '}), 400
    if "proxy" not in request.json:
        return jsonify({'error': 'expected request with proxy'}), 400

    proxy = request.json['proxy']
    err, msg = YamlDB.update_proxy(KUBAM_CFG, proxy)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'proxy' : proxy}), 201


# get the public keys
@app.route(API_ROOT + "/keys", methods=['GET'])
@cross_origin()
def get_public_keys():
    err, msg, keys = YamlDB.get_public_keys(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'keys' : keys}), 200


# update public keys
@app.route(API_ROOT + "/keys", methods=['POST'])
@cross_origin()
def update_public_keys():
    if not request.json:
        return jsonify({'error': 'expected request with keys '}), 400
    if "keys" not in request.json:
        return jsonify({'error': 'expected request with keys '}), 400

    keys = request.json['keys']
    err, msg = YamlDB.update_public_keys(KUBAM_CFG, keys)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'keys' : keys}), 201

    
# get the networks in the UCS. 
@app.route(API_ROOT + "/networks", methods=['GET'])
@cross_origin()
def get_networks():
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    vlans = UCSNet.listVLANs(handle) 
    logout(handle)
    err, msg, net_hash = YamlDB.get_network(KUBAM_CFG)
    err, msg, net_settings = YamlDB.get_ucs_network(KUBAM_CFG)
    selected_vlan = ""
    if "vlan" in net_settings:
        selected_vlan = net_settings["vlan"]
       
    return jsonify({'vlans': [{"name": vlan.name, "id": vlan.id, "selected": (vlan.name == selected_vlan)}  for vlan in vlans], 'network' : net_hash}), 200
                    

@app.route(API_ROOT + "/networks/vlan", methods=['POST'])
@cross_origin()
def select_vlan():
    if not request.json:
        return jsonify({'error': 'expected hash of VLANs'}), 400
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    #app.logger.info("Request is: ")
    #app.logger.info(request)
    vlan = request.json['vlan']
    err, msg = YamlDB.update_ucs_network(KUBAM_CFG, {"vlan": vlan})
    if err != 0:
        return jsonify({'error': msg}), 500
    # return the existing networks now with the new one chosen. 
    return get_networks()
    

@app.route(API_ROOT + "/networks", methods=['POST'])
@cross_origin()
def update_networks():
    if not request.json:
        return jsonify({'error': 'expected hash of network settings'}), 400
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    #app.logger.info("request is")
    #app.logger.info(request.json)
    vlan = request.json['vlan']
    err, msg = YamlDB.update_ucs_network(KUBAM_CFG, {"vlan": vlan})
    if err != 0:
        return jsonify({'error': msg}), 400
    network = request.json['network']
    err, msg = YamlDB.update_network(KUBAM_CFG, network)
    if err != 0:
        return jsonify({'error': msg}), 400
    return get_networks()

    
# see if there are any selected servers in the database 
def servers_to_api(ucs_servers, dbServers):
    for i, real_server in enumerate(ucs_servers):
        if real_server["type"] == "blade":
            if "blades" in dbServers:
                for b in dbServers["blades"]:
                    b_parts = b.split("/")
                    if (    len(b_parts) == 2 and 
                            real_server["chassis_id"] == b_parts[0] and 
                            real_server["slot"] == b_parts[1]):
                        real_server["selected"] = True
                        ucs_servers[i] = real_server
        elif real_server["type"] == "rack":
            if "rack_servers" in dbServers:
                for s in dbServers["rack_servers"]:
                    if real_server["rack_id"] == s:
                        real_server["selected"] = True
                        ucs_servers[i] = real_server
    return ucs_servers


@app.route(API_ROOT + "/servers", methods=['GET'])
@cross_origin()
def get_servers():
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    servers = UCSServer.list_servers(handle) 
    logout(handle)
  
    # gets a hash of severs of form:    
    # {blades: ["1/1", "1/2",..], rack: ["6", "7"]}
    err, msg, dbServers = YamlDB.get_ucs_servers(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    servers = servers_to_api(servers, dbServers) 
    #app.logger.info("returninng servers...")
    #app.logger.info(servers)
    err, msg, hosts = YamlDB.get_hosts(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'servers': servers, 'hosts': hosts}), 200


# translates the json we get from the web interface to what we expect to put in 
# the database.
def servers_to_db(servers):
    # gets a server array list and gets the selected servers and
    # puts them in the database form
    server_pool = {}
    #app.logger.info(servers)
    for s in servers:
        if "selected" in s and s["selected"] == True:
            if s["type"] == "blade":
                if not "blades" in server_pool:
                    server_pool["blades"] = []
                b = "%s/%s" % (s["chassis_id"] , s["slot"])
                server_pool["blades"].append(b)
            elif s["type"] == "rack":
                if not "rack_servers" in server_pool:
                    server_pool["rack_servers"] = []
                server_pool["rack_servers"].append(s["rack_id"])
    return server_pool

@app.route(API_ROOT + "/servers", methods=['POST'])
@cross_origin()
def select_servers():
    # make sure we got some data.
    if not request.json:
        return jsonify({'error': 'expected hash of servers'}), 400
    # make sure we can login
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    servers = request.json['servers']
    # we expect servers to be a hash of like:
    # {blades: ["1/1", "1/2",..], rack: ["6", "7"]}
    servers = servers_to_db(servers)
    if servers:
        err, msg = YamlDB.update_ucs_servers(KUBAM_CFG, servers)
        if err != 0:
            return jsonify({'error': msg}), 400
    if "hosts" not in request.json:
        return get_servers()
    
    hosts = request.json['hosts']
    err, msg = YamlDB.update_hosts(KUBAM_CFG, hosts)
    if err != 0:
        return jsonify({'error': msg}), 400
    
    # return the existing networks now with the new one chosen. 
    return get_servers()



# list ISO images.
@app.route(API_ROOT + "/isos", methods=['GET'])
@cross_origin()
def get_isos():
    err, isos = IsoMaker.list_isos("/kubam")    
    if err != 0:
        return jsonify({'error': isos})
    return jsonify({'isos': isos}), 200

# DO NOT USE
# This API is only for extracting unknown ISOs.  We can put the iso as well as the directory name we want to extract to.  Use /isos/boot
# extract an ISO image. This probably isn't used as the /isos/boot does this for you as part of the 
# creation process. 
# curl -H "Content-Type: application/json" -X POST -d '{"iso" : "Vmware-ESXi-6.5.0-4564106-Custom-Cisco-6.5.0.2.iso", "os": "esxi6.5" }' http://localhost/api/v1/isos/extract
@app.route(API_ROOT + "/isos/extract", methods=['POST'])
@cross_origin()
def extract_iso():
    if not request.json:
        return jsonify({'error': 'expected iso hash'}), 400
    iso = request.json['iso']
    os = request.json['os']
    err, msg = IsoMaker.extract_iso("/kubam/" + iso, "/kubam/" + os) 
    if not err == 0:
        return jsonify({"error": msg}), 500
    return jsonify({"status": "ok"}), 201

# make the boot ISO image of an ISO
# curl -H "Content-Type: application/json" -X POST -d '{"iso" : "Vmware-ESXi-6.5.0-4564106-Custom-Cisco-6.5.0.2.iso" }' http://localhost/api/v1/isos/boot
# curl -H "Content-Type: application/json" -X POST -d '{"iso" : "CentOS-7-x86_64-Minimal-1611.iso" }' http://localhost/api/v1/isos/boot
@app.route(API_ROOT + "/isos/boot", methods=['POST'])
@cross_origin()
def mkboot_iso():
    # get the iso map
    err, msg, isos = YamlDB.get_iso_map(KUBAM_CFG)
    if err != 0:
        return jsonify({"error": msg}), 400
    if len(isos) == 0:
        return jsonify({"error": "No ISOS have been mapped.  Please map an ISO image with an OS"}), 400
    err, msg = IsoMaker.mkboot_iso(isos)
    if err != 0:
        return jsonify({"error": msg}), 400

    err, msg = Builder.deploy_server_images(KUBAM_CFG)
    if err != 0:
        return jsonify({"error": msg}), 400
    return jsonify({"status": "ok"}), 201
    

# get the capabilities of KUBAM
@app.route(API_ROOT + "/catalog", methods=['GET'])
@cross_origin()
def get_catalog():
    catalog = Builder.catalog
    app.logger.info(catalog)
    return jsonify(catalog), 200


#map the iso images to os versions. 
@app.route(API_ROOT + "/isos/map", methods=['GET'])
@cross_origin()
def get_iso_map():
    err, msg, isos = YamlDB.get_iso_map(KUBAM_CFG)
    if err != 0:
        return jsonify({'error': msg}), 400
    return jsonify({'iso_map' : isos}), 200

# update iso to os map
@app.route(API_ROOT + "/isos/map", methods=['POST'])
@cross_origin()
def update_iso_map():
    app.logger.info("request.json")
    app.logger.info(request.json)
    if not request.json:
        return jsonify({'error': 'expected request with iso_map '}), 400
    if "iso_map" not in request.json:
        return jsonify({'error': 'expected request with iso_map '}), 400

    isos = request.json['iso_map']
    err, msg = YamlDB.update_iso_map(KUBAM_CFG, isos)
    if err != 0:
        return jsonify({'error': msg}), 400
    return get_iso_map()



# Make the server images
@app.route(API_ROOT + "/servers/images", methods=['POST'])
@cross_origin()
def deploy_server_autoinstall_images():
    err, msg = Builder.deploy_server_images(KUBAM_CFG)
    if not err == 0:
        return jsonify({"error": msg})
    return jsonify({"status": "ok"}), 201

#stage2: make the UCS configuration using the kubam information. 
def make_ucs():
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    #TODO: make so we can specify orgs in kubam. Right now its hard coded. 
    err, msg = UCSUtil.create_org(handle, "kubam")
    if err != 0: 
        logout(handle)
        return err, msg 
    err, msg, net_settings = YamlDB.get_ucs_network(KUBAM_CFG)
    selected_vlan = ""
    if "vlan" in net_settings:
        selected_vlan = net_settings["vlan"]
    if selected_vlan == "":
        logout(handle)
        return 1, "No vlan selected in UCS configuration."
    err, msg = UCSNet.createKubeNetworking(handle, "org-root/org-kubam", selected_vlan)
    if err != 0:
        logout(handle)
        return err, msg

    # get the selected servers, and hosts.
    err, msg, hosts = YamlDB.get_hosts(KUBAM_CFG)
    err, msg, servers = YamlDB.get_ucs_servers(KUBAM_CFG)
    err, msg, kubam_ip = YamlDB.get_kubam_ip(KUBAM_CFG)
    err, msg = UCSServer.createKubeServers(handle, "org-root/org-kubam", hosts, servers, kubam_ip)
    if err != 0:
        logout(handle)
        return err, msg
    
    logout(handle)
    return err, msg
    

@app.route(API_ROOT + "/settings", methods=['POST'])
@cross_origin()
def update_settings():
    app.logger.info(request.json)
    if not request.json:
        return jsonify({'error': 'expected kubam_ip and keys in json request'}), 400
    if not "kubam_ip" in request.json:
        return jsonify({'error': 'expected kubam_ip in json request.'}), 400
    if not "keys" in request.json:
        return jsonify({'error': 'expected keys in json request.'}), 400
    if not "proxy" in request.json:
        return jsonify({'error': 'expected proxy in json request.'}), 400
    app.logger.info(request.json)
    # update the kubam_IP if it is changed.     
    ip = request.json['kubam_ip']
    err, msg = YamlDB.update_kubam_ip(KUBAM_CFG, ip)
    if err != 0:
        return jsonify({'error': msg}), 400

    proxy = request.json['proxy']
    err, msg = YamlDB.update_proxy(KUBAM_CFG, proxy)
    if err != 0:
        return jsonify({'error': msg}), 400

    # update the keys if changed. 
    keys = request.json['keys']
    app.logger.info(keys)
    err, msg = YamlDB.update_public_keys(KUBAM_CFG, keys)
    if err != 0:
        return jsonify({'error': msg}), 400



    return jsonify({"status": "ok"}), 201

# the grand daddy of them all.  It is what deploys everything. 
@app.route(API_ROOT + "/deploy", methods=['POST'])
@cross_origin()
def deploy():
    err, msg = make_ucs()
    if err != 0:
        return jsonify({'error': msg}), 400
   
    # now call the deployment!    
    return jsonify({"status": "ok"}), 201


# dangerous command!  Will undo everything!
@app.route(API_ROOT + "/deploy", methods=['DELETE'])
@cross_origin()
def destroy():
    app.logger.info("Deleting deployment")
    err, msg, handle = login()
    if err != 0: 
        return not_logged_in(msg) 
    err, msg, hosts = YamlDB.get_hosts(KUBAM_CFG)
    if err != 0: 
        return jsonify({'error': msg}), 400
    if len(hosts) == 0:
        return jsonify({"status": "no servers deployed"}),  200
    err, msg = UCSServer.deleteKubeServers(handle, "org-root/org-kubam", hosts)
    if err != 0: 
        return jsonify({'error': msg}), 400
    err, msg = UCSNet.deleteKubeNetworking(handle, "org-root/org-kubam")
    if err != 0: 
        return jsonify({'error': msg}), 400
    return jsonify({"status": "ok"}), 201


if __name__ == '__main__':
    app.run(debug=True)

