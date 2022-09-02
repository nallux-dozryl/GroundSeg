import json, subprocess, requests
from wireguard import Wireguard
from urbit_docker import UrbitDocker
import time
import sys

class Orchestrator:
    
    _urbits = {}


    def __init__(self, config_file):

        self.config_file = config_file
        # Load config
        with open(config_file) as f:
            self.config = json.load(f)

        # First boot setup
        if(self.config['firstBoot']):
            self.first_boot()
            self.config['firstBoot'] = False
            self.save_config()

        # get wireguard netowkring information
        # Load urbits with wg info
        # start wireguard
        self.wireguard = Wireguard(self.config)
        # TODO add this as a function so that a key can be sent through web interface
        self.wireguard.registerDevice(self.config['reg_key']) 
        self.anchor_config = self.wireguard.getStatus()
        self.wireguard.start()

        self.load_urbits()

    def load_urbits(self):
        for p in self.config['piers']:
            data = None
            with open(f'settings/{p}.json') as f:
                data = json.load(f)
            self._urbits[p] = UrbitDocker(data)

    def registerUrbit(self, patp):
       for ep in self.anchor_config['subdomains']:
          if(patp in ep['url']):
              return

       self.wireguard.registerService(f'{patp}','urbit-web')
       self.wireguard.registerService(f'ames.{patp}','urbit-ames')
       self.wireguard.registerService(f's3.{patp}','minio')
       self.anchor_config = self.wireguard.getStatus()

    def addUrbit(self, patp, urbit):
        self.config['piers'].append(patp)
        self.registerUrbit(patp)
        url = None
        http_port = None
        ames_port = None
        s3_port = None
        for ep in self.anchor_config['subdomains']:
            if(f'{patp}.nativeplanet.live' == ep['url']):
                url = ep['url']
                http_port = ep['port']
            elif(f'ames.{patp}.nativeplanet.live' == ep['url']):
                ames_port = ep['port']
            elif(f's3.{patp}.nativeplanet.live' == ep['url']):
                s3_port = ep['port']

        urbit.setWireguardNetwork(url, http_port, ames_port, s3_port)
        self._urbits[patp] = urbit
        self.save_config()
        

    def removeUrbit(self, patp):
        urb = self._urbits[patp]
        urb.removeUrbit()
        urb = self._urbits.pop(patp)
        self.config['piers'].remove(patp)
        self.save_config()


    def getUrbits(self):
        urbits= []

        for urbit in self._urbits.values():
            u = dict()
            u['name'] = urbit.pier_name
            u['running'] = urbit.isRunning();
            if(urbit.config['network']=='wireguard'):
                u['url'] = f"http://{urbit.config['wg_url']}"
            else:
                u['url'] = f'http://nativeplanet.local:{urbit.config["http_port"]}'
            if(urbit.isRunning()):
                u['code'] = urbit.get_code().decode('utf-8')
            else:
                u['code'] = ""

            u['network'] = urbit.config['network']
            
            urbits.append(u)

        return urbits
    
    def getContainers(self):
        containers = list(self._urbits.keys())
        containers.append('wireguard')
        containers.append('minio')
        return containers

    def switchUrbitNetwork(self, urbit_name):
        urbit = self._urbits[urbit_name]
        network = 'none'
        url = f"nativeplanet.local:{urbit.config['http_port']}"

        if(urbit.config['network'] == 'none'):
            network = 'wireguard'
            url = urbit.config['url']

        urbit.setNetwork(network);
        time.sleep(2)

        

    def getOpenUrbitPort(self):
        http_port = 8080
        ames_port = 34343

        for u in self._urbits.values():
            if(u.config['http_port'] >= http_port):
                http_port = u.config['http_port']
            if(u.config['ames_port'] >= ames_port):
                ames_port = u.config['ames_port']

        return http_port+1, ames_port+1

    def getLogs(self, container):
        if container == 'wireguard':
            return self.wireguard.wg_docker.logs()
        if container == 'minio':
            return "" #TODO add minio container to orch
        if container in self._urbits.keys():
            return self._urbits[container].logs()
        return ""


    def first_boot(self):
        subprocess.run("wg genkey > privkey", shell=True)
        subprocess.run("cat privkey| wg pubkey | base64 -w 0 > pubkey", shell=True)

        # Load priv and pub key
        with open('pubkey') as f:
           self.config['pubkey'] = f.read().strip()
        with open('privkey') as f:
           self.config['privkey'] = f.read().strip()
        #clean up files
        subprocess.run("rm privkey pubkey", shell =True)
   

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent = 4)




if __name__ == '__main__':
    orchestrator = Orchestrator("settings/system.json")
