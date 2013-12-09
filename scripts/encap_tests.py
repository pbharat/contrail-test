# Need to import path to test/fixtures and test/scripts/
# Ex : export PYTHONPATH='$PATH:/root/test/fixtures/:/root/test/scripts/'
# 
# To run tests, you can do 'python -m testtools.run mx_tests'. To run specific tests,
# You can do 'python -m testtools.run -l mx_test'
# Set the env variable PARAMS_FILE to point to your ini file. Else it will try to pick params.ini in PWD
# Set the env variable MX_GW_TESTto 1 to run the test 
#
import os
from novaclient import client as mynovaclient
from novaclient import exceptions as novaException
import unittest
import fixtures
import testtools
import socket

from contrail_test_init import *
from vn_test import *
from quantum_test import *
from vnc_api_test import *
from nova_test import *
from vm_test import *
from connections import ContrailConnections
from floating_ip import *
from policy_test import *
from contrail_fixtures import *
from control_node import *
from tcutils.wrappers import preposttest_wrapper
from tcutils.commands import ssh, execute_cmd, execute_cmd_out

class TestEncapsulation(testtools.TestCase, fixtures.TestWithFixtures):
    
#    @classmethod
    def setUp(self):
        super(TestEncapsulation, self).setUp()  
        if 'PARAMS_FILE' in os.environ :
            self.ini_file= os.environ.get('PARAMS_FILE')
        else:
            self.ini_file= 'params.ini'
        self.inputs=self.useFixture(ContrailTestInit( self.ini_file))
        self.connections= ContrailConnections(self.inputs)        
        self.quantum_fixture= self.connections.quantum_fixture
        self.nova_fixture = self.connections.nova_fixture
        self.vnc_lib= self.connections.vnc_lib
        self.logger= self.inputs.logger
        self.analytics_obj=self.connections.analytics_obj
    #end setUpClass
    
    def cleanUp(self):
        super(TestEncapsulation, self).cleanUp()
    #end cleanUp
    
    def runTest(self):
        pass
    #end runTest
    
    @preposttest_wrapper
    def test_encaps_mx_gateway (self):
        '''Test to validate floating-ip froma a public pool  assignment to a VM. It creates a VM, assigns a FIP to it and pings to outside the cluster.'''

        if (('MX_GW_TEST' in os.environ) and (os.environ.get('MX_GW_TEST') == '1')):
            if len(set(self.inputs.compute_ips)) < 2 :
                raise self.skipTest('Skiping Test. At least 2 compute node required to run the test')

            self.logger.info('Deleting any Encap before continuing')
            out=self.connections.delete_vrouter_encap()
            if ( out!='No config id found'):
                self.addCleanup(self.connections.set_vrouter_config_encap,out[0],out[1],out[2])

            self.logger.info('Setting new Encap before continuing')
            config_id=self.connections.set_vrouter_config_encap('MPLSoUDP','MPLSoGRE','VXLAN')
            self.logger.info('Created.UUID is %s'%(config_id))
            self.addCleanup(self.connections.delete_vrouter_encap)

            result= True
            fip_pool_name= self.inputs.fip_pool_name
            fvn_name= 'public100'
            fip_subnets= [self.inputs.fip_pool]
            vm1_name= 'vm200'
            vn1_name= 'vn200'
            vn1_subnets= ['11.1.1.0/24']
            api_server_port = self.inputs.api_server_port
            api_server_ip = self.inputs.cfgm_ip
            mx_rt=self.inputs.mx_rt
            router_name =self.inputs.ext_routers[0][0]
            router_ip=self.inputs.ext_routers[0][1]

            fvn_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=fvn_name, inputs= self.inputs, subnets= fip_subnets, router_asn=self.inputs.router_asn, rt_number=mx_rt))
            assert fvn_fixture.verify_on_setup()
            vn1_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=vn1_name, inputs= self.inputs, subnets= vn1_subnets))
            assert vn1_fixture.verify_on_setup()
            vm1_fixture= self.useFixture(VMFixture(project_name= self.inputs.project_name, connections= self.connections, vn_obj= vn1_fixture.obj, vm_name= vm1_name))
            assert vm1_fixture.verify_on_setup()

            fip_fixture= self.useFixture(FloatingIPFixture( project_name= self.inputs.project_name, inputs = self.inputs, connections= self.connections, pool_name = fip_pool_name, vn_id= fvn_fixture.vn_id ))
            assert fip_fixture.verify_on_setup()
            fip_id= fip_fixture.create_and_assoc_fip( fvn_fixture.vn_id, vm1_fixture.vm_id)
            assert fip_fixture.verify_fip( fip_id, vm1_fixture, fvn_fixture )
            routing_instance=fvn_fixture.ri_name

            # Configuring all control nodes here
            for entry in self.inputs.bgp_ips:
                hostname= self.inputs.host_data[entry]['name']
                entry_control_ip= self.inputs.host_data[entry]['host_control_ip']
                cn_fixture1= self.useFixture(CNFixture(connections= self.connections,
                      router_name=hostname, router_ip= entry_control_ip, router_type = 'contrail', inputs= self.inputs))
            cn_fixturemx= self.useFixture(CNFixture(connections= self.connections,
                  router_name=router_name, router_ip= router_ip, router_type = 'mx', inputs= self.inputs))
            sleep(10)
            assert cn_fixturemx.verify_on_setup()
            # TODO Configure MX. Doing Manually For Now
            self.logger.info( "BGP Peer configuraion done and trying to outside the VN cluster")
            self.logger.info( "Checking the basic routing. Pinging known local IP bng2-core-gw1.jnpr.net")
            assert vm1_fixture.ping_with_certainty('10.206.255.2')
            self.logger.info( "Now trying to ping www-int.juniper.net")
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty( 'www-int.juniper.net' , count = '15'):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'GRE')
            fip_fixture.disassoc_and_delete_fip(fip_id)
            if not result :
                self.logger.error('Test  ping outside VN cluster from VM %s failed' %(vm1_name))
                assert result
        else:
            self.logger.info('Testcase test_mx_gateway for now only need to be run in BLR Sanity Setup')
   
        return True
    # end test_encaps_mx_gateway

    @preposttest_wrapper
    def test_apply_policy_fip_on_same_vn_gw_mx (self):
        '''A particular VN is configure with policy to talk accross VN's and FIP to access outside'''

        if (('MX_GW_TEST' in os.environ) and (os.environ.get('MX_GW_TEST') == '1')):

            if len(set(self.inputs.compute_ips)) < 2 :
                self.logger.info ("Skiping Test. At least 2 compute node required to run the test")
                raise self.skipTest('Skiping Test. At least 2 compute node required to run the test')

            self.logger.info('Deleting any Encap before continuing')
            out=self.connections.delete_vrouter_encap()
            if ( out!='No config id found'):
                self.addCleanup(self.connections.set_vrouter_config_encap,out[0],out[1],out[2])

            self.logger.info('Setting new Encap before continuing')
            config_id=self.connections.set_vrouter_config_encap('MPLSoUDP','MPLSoGRE','VXLAN')
            self.logger.info('Created.UUID is %s'%(config_id))
            self.addCleanup(self.connections.delete_vrouter_encap)

            result= True
            fip_pool_name= self.inputs.fip_pool_name
            fvn_name= 'public100'
            fip_subnets= [self.inputs.fip_pool]
            vm1_name= 'vm200'
            vn1_name= 'vn200'
            vn1_subnets= ['11.1.1.0/24']
            vm2_name= 'vm300'
            vn2_name= 'vn300'
            vn2_subnets= ['22.1.1.0/24']
            api_server_port = self.inputs.api_server_port
            api_server_ip = self.inputs.cfgm_ip
            mx_rt=self.inputs.mx_rt
            router_name =self.inputs.ext_routers[0][0]
            router_ip=self.inputs.ext_routers[0][1]
            # Get all compute host
            host_list=[]
            for host in self.inputs.compute_ips: host_list.append(self.inputs.host_data[host]['name'])

            fvn_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=fvn_name, inputs= self.inputs, subnets= fip_subnets, router_asn=self.inputs.router_asn, rt_number=mx_rt))
            assert fvn_fixture.verify_on_setup()
            vn1_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=vn1_name, inputs= self.inputs, subnets= vn1_subnets))
            assert vn1_fixture.verify_on_setup()
            vm1_fixture= self.useFixture(VMFixture(project_name= self.inputs.project_name, connections= self.connections, vn_obj= vn1_fixture.obj, vm_name= vm1_name, node_name= host_list[0]))
            assert vm1_fixture.verify_on_setup()

            vn2_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=vn2_name, inputs= self.inputs, subnets= vn2_subnets))
            assert vn2_fixture.verify_on_setup()
            vm2_fixture= self.useFixture(VMFixture(project_name= self.inputs.project_name, connections= self.connections, vn_obj= vn2_fixture.obj, vm_name= vm2_name, node_name= host_list[1]))
            assert vm2_fixture.verify_on_setup()
           
            # Fip 
            fip_fixture= self.useFixture(FloatingIPFixture( project_name= self.inputs.project_name, inputs = self.inputs, connections= self.connections, pool_name = fip_pool_name, vn_id= fvn_fixture.vn_id ))
            assert fip_fixture.verify_on_setup()
            fip_id= fip_fixture.create_and_assoc_fip( fvn_fixture.vn_id, vm1_fixture.vm_id)
            self.addCleanup( fip_fixture.disassoc_and_delete_fip, fip_id)
            assert fip_fixture.verify_fip( fip_id, vm1_fixture, fvn_fixture )
            routing_instance=fvn_fixture.ri_name

            # Configuring all control nodes here
            for entry in self.inputs.bgp_ips:
                hostname= self.inputs.host_data[entry]['name']
                entry_control_ip= self.inputs.host_data[entry]['host_control_ip']
                cn_fixture1= self.useFixture(CNFixture(connections= self.connections,
                      router_name=hostname, router_ip= entry_control_ip, router_type = 'contrail', inputs= self.inputs))
            cn_fixturemx= self.useFixture(CNFixture(connections= self.connections,
                  router_name=router_name, router_ip= router_ip, router_type = 'mx', inputs= self.inputs))
            sleep(10) 
            assert cn_fixturemx.verify_on_setup()

            # Policy
            # Apply policy in between VN
            policy1_name= 'policy1'
            policy2_name= 'policy2'
            rules= [
                {
                   'direction'     : '<>', 'simple_action' : 'pass',
                   'protocol'      : 'icmp',
                   'source_network': vn1_name,
                   'dest_network'  : vn2_name,
                 },
                    ]
            rev_rules= [
                {
                   'direction'     : '<>', 'simple_action' : 'pass',
                   'protocol'      : 'icmp',
                   'source_network': vn2_name,
                   'dest_network'  : vn1_name,
                 },
                    ]

            policy1_fixture= self.useFixture( PolicyFixture( policy_name= policy1_name, rules_list= rules, inputs= self.inputs, connections= self.connections ))
            policy2_fixture= self.useFixture( PolicyFixture( policy_name= policy2_name, rules_list= rev_rules, inputs= self.inputs, connections= self.connections ))

            self.logger.info('Apply policy between VN %s and %s' %(vn1_name,vn2_name))
            vn1_fixture.bind_policies([policy1_fixture.policy_fq_name], vn1_fixture.vn_id)
            self.addCleanup(vn1_fixture.unbind_policies , vn1_fixture.vn_id ,[policy1_fixture.policy_fq_name])
            vn2_fixture.bind_policies([policy2_fixture.policy_fq_name], vn2_fixture.vn_id)
            self.addCleanup(vn2_fixture.unbind_policies , vn2_fixture.vn_id ,[policy2_fixture.policy_fq_name])

            
            self.logger.info('Checking connectivity within VNS cluster through Policy')
            self.logger.info('Ping from %s to %s' %(vm1_name,vm2_name))
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty(vm2_fixture.vm_ip, count = '15'):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            comp_vm2_ip = vm2_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'UDP')
            self.tcpdump_analyze_on_compute(comp_vm2_ip,'UDP')

            self.logger.info('Checking connectivity outside VNS cluster through FIP')
            self.logger.info( "Checking the basic routing. Pinging known local IP bng2-core-gw1.jnpr.net")
            assert vm1_fixture.ping_with_certainty('10.206.255.2')
            self.logger.info( "Now trying to ping www-int.juniper.net")
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty( 'www-int.juniper.net', count = '15' ):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'GRE')
            if not result :
                self.logger.error('Test to verify the Traffic to Inside and Outside Virtual network cluster simaltaneiously failed')
                assert result
        else:
            self.logger.info('Testcase test_traffic_within_and_ouside_vns for now only need to be run in BLR Sanity Setup')

        return True
    # end test_apply_policy_fip_on_same_vn_gw_mx

    @preposttest_wrapper
    def test_apply_policy_fip_vn_with_encaps_change_gw_mx (self):
        '''A particular VN is configured with policy to talk across VN's and FIP to access outside.The encapsulation prioritis set at the start of testcase are changed and verified '''

        if (('MX_GW_TEST' in os.environ) and (os.environ.get('MX_GW_TEST') == '1')):

            if len(set(self.inputs.compute_ips)) < 2 :
                self.logger.info ("Skiping Test. At least 2 compute node required to run the test")
                raise self.skipTest('Skiping Test. At least 2 compute node required to run the test')

            self.logger.info('Deleting any Encap before continuing')
            out=self.connections.delete_vrouter_encap()
            if ( out!='No config id found'):
                self.addCleanup(self.connections.set_vrouter_config_encap,out[0],out[1],out[2])

            self.logger.info('Setting new Encap before continuing')
            config_id=self.connections.set_vrouter_config_encap('MPLSoUDP','MPLSoGRE','VXLAN')
            self.logger.info('Created.UUID is %s'%(config_id))
            self.addCleanup(self.connections.delete_vrouter_encap)

            result= True
            fip_pool_name= self.inputs.fip_pool_name
            fvn_name= 'public100'
            fip_subnets= [self.inputs.fip_pool]
            vm1_name= 'vm200'
            vn1_name= 'vn200'
            vn1_subnets= ['11.1.1.0/24']
            vm2_name= 'vm300'
            vn2_name= 'vn300'
            vn2_subnets= ['22.1.1.0/24']
            api_server_port = self.inputs.api_server_port
            api_server_ip = self.inputs.cfgm_ip
            mx_rt=self.inputs.mx_rt
            router_name =self.inputs.ext_routers[0][0]
            router_ip=self.inputs.ext_routers[0][1]
            # Get all compute host
            host_list=[]
            for host in self.inputs.compute_ips: host_list.append(self.inputs.host_data[host]['name'])

            fvn_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=fvn_name, inputs= self.inputs, subnets= fip_subnets, router_asn=self.inputs.router_asn, rt_number=mx_rt))
            assert fvn_fixture.verify_on_setup()
            vn1_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=vn1_name, inputs= self.inputs, subnets= vn1_subnets))
            assert vn1_fixture.verify_on_setup()
            vm1_fixture= self.useFixture(VMFixture(project_name= self.inputs.project_name, connections= self.connections, vn_obj= vn1_fixture.obj, vm_name= vm1_name, node_name= host_list[0]))
            assert vm1_fixture.verify_on_setup()

            vn2_fixture= self.useFixture(VNFixture(project_name= self.inputs.project_name, connections= self.connections, vn_name=vn2_name, inputs= self.inputs, subnets= vn2_subnets))
            assert vn2_fixture.verify_on_setup()
            vm2_fixture= self.useFixture(VMFixture(project_name= self.inputs.project_name, connections= self.connections, vn_obj= vn2_fixture.obj, vm_name= vm2_name, node_name= host_list[1]))
            assert vm2_fixture.verify_on_setup()

            # Fip
            fip_fixture= self.useFixture(FloatingIPFixture( project_name= self.inputs.project_name, inputs = self.inputs, connections= self.connections, pool_name = fip_pool_name, vn_id= fvn_fixture.vn_id ))
            assert fip_fixture.verify_on_setup()
            fip_id= fip_fixture.create_and_assoc_fip( fvn_fixture.vn_id, vm1_fixture.vm_id)
            self.addCleanup( fip_fixture.disassoc_and_delete_fip, fip_id)
            assert fip_fixture.verify_fip( fip_id, vm1_fixture, fvn_fixture )
            routing_instance=fvn_fixture.ri_name

            # Configuring all control nodes here
            for entry in self.inputs.bgp_ips:
                hostname= self.inputs.host_data[entry]['name']
                entry_control_ip= self.inputs.host_data[entry]['host_control_ip']
                cn_fixture1= self.useFixture(CNFixture(connections= self.connections,
                      router_name=hostname, router_ip= entry_control_ip, router_type = 'contrail', inputs= self.inputs))
            cn_fixturemx= self.useFixture(CNFixture(connections= self.connections,
                  router_name=router_name, router_ip= router_ip, router_type = 'mx', inputs= self.inputs))
            sleep(10)
            assert cn_fixturemx.verify_on_setup()

            # Policy
            # Apply policy in between VN
            policy1_name= 'policy1'
            policy2_name= 'policy2'
            rules= [
                {
                   'direction'     : '<>', 'simple_action' : 'pass',
                   'protocol'      : '1',
                   'source_network': vn1_name,
                   'dest_network'  : vn2_name,
                 },
                    ]
            rev_rules= [
                {
                   'direction'     : '<>', 'simple_action' : 'pass',
                   'protocol'      : '1',
                   'source_network': vn2_name,
                   'dest_network'  : vn1_name,
                 },
                    ]

            policy1_fixture= self.useFixture( PolicyFixture( policy_name= policy1_name, rules_list= rules, inputs= self.inputs, connections= self.connections ))
            policy2_fixture= self.useFixture( PolicyFixture( policy_name= policy2_name, rules_list= rev_rules, inputs= self.inputs, connections= self.connections ))

            self.logger.info('Apply policy between VN %s and %s' %(vn1_name,vn2_name))
            vn1_fixture.bind_policies([policy1_fixture.policy_fq_name], vn1_fixture.vn_id)
            self.addCleanup(vn1_fixture.unbind_policies , vn1_fixture.vn_id ,[policy1_fixture.policy_fq_name])
            vn2_fixture.bind_policies([policy2_fixture.policy_fq_name], vn2_fixture.vn_id)
            self.addCleanup(vn2_fixture.unbind_policies , vn2_fixture.vn_id ,[policy2_fixture.policy_fq_name])

            self.logger.info('Checking connectivity within VNS cluster through Policy')
            self.logger.info('Ping from %s to %s' %(vm1_name,vm2_name))
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty(vm2_fixture.vm_ip, count = '15'):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            comp_vm2_ip = vm2_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'UDP')
            self.tcpdump_analyze_on_compute(comp_vm2_ip,'UDP')

            self.logger.info('Checking connectivity outside VNS cluster through FIP')
            self.logger.info( "Checking the basic routing. Pinging known local IP bng2-core-gw1.jnpr.net")
            assert vm1_fixture.ping_with_certainty('10.206.255.2')
            self.logger.info( "Now trying to ping www-int.juniper.net")
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty( 'www-int.juniper.net', count = '15' ):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'GRE')
            if not result :
                self.logger.error('Test to verify the Traffic to Inside and Outside Virtual network cluster simaltaneiously failed')
                assert result
            self.logger.info('Now changing the encapsulation priorities')
            self.logger.info('The new encapsulation will take effect once bug 1422 is fixed')
            res=self.connections.update_vrouter_config_encap('MPLSoGRE','MPLSoUDP','VXLAN')
            self.logger.info('Updated.%s'%(res))
            self.logger.info('Checking connectivity within VNS cluster through Policy')
            self.logger.info('Ping from %s to %s' %(vm1_name,vm2_name))
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty(vm2_fixture.vm_ip, count = '15'):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            comp_vm2_ip = vm2_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'GRE')
            self.tcpdump_analyze_on_compute(comp_vm2_ip,'GRE')

            self.logger.info('Checking connectivity outside VNS cluster through FIP')
            self.logger.info( "Checking the basic routing. Pinging known local IP bng2-core-gw1.jnpr.net")
            assert vm1_fixture.ping_with_certainty('10.206.255.2')
            self.logger.info( "Now trying to ping www-int.juniper.net")
            self.tcpdump_start_on_all_compute()
            if not vm1_fixture.ping_with_certainty( 'www-int.juniper.net', count = '15' ):
                result = result and False
            comp_vm1_ip = vm1_fixture.vm_node_ip
            self.tcpdump_analyze_on_compute(comp_vm1_ip,'GRE')
            if not result :
                self.logger.error('Test to verify the Traffic to Inside and Outside Virtual network cluster simaltaneiously failed after changing the encapsulation')
                assert result

        else:
            self.logger.info('Testcase test_traffic_within_and_ouside_vns for now only need to be run in BLR Sanity Setup')
    # end test_apply_policy_fip_vn_with_encaps_change_gw_mx


#end TestEncapsulation

###############################################################################################################################

    def start_tcpdump(self, session, cmd):
        self.logger.info("Starting tcpdump to capture the packets.")
        result = execute_cmd(session, cmd, self.logger)
   #end start_tcpdump

    def stop_tcpdump(self, session):
        self.logger.info("Stopping any tcpdump process running")
        cmd = 'kill $(pidof tcpdump)'
        execute_cmd(session, cmd, self.logger)
        self.logger.info("Removing any encap-pcap files in /tmp")
        cmd = 'rm -f /tmp/encap*pcap' 
        execute_cmd(session, cmd, self.logger)
    #end stop_tcpdump    


    def tcpdump_start_on_all_compute(self):
        for compute_ip in self.inputs.compute_ips:
            session = ssh(compute_ip,'root','c0ntrail123')
            self.stop_tcpdump(session)
            cmd="cat /etc/contrail/agent.conf | grep -oP '(?<=<name>).*?(?=</name></eth-port>)'"
            comp_intf, err = execute_cmd_out(session, cmd, self.logger)
            comp_intf = comp_intf[:-1]
            pcap1 = '/tmp/encap-udp.pcap'
            pcap2 = '/tmp/encap-gre.pcap'
            cmd1='tcpdump -ni %s udp port 51234 -w %s'%(comp_intf, pcap1)
            cmd_udp="nohup " + cmd1 + " >& /dev/null < /dev/null &"
            cmd2='tcpdump -ni %s proto 47 -w %s'% (comp_intf, pcap2)
            cmd_gre="nohup " + cmd2 + " >& /dev/null < /dev/null &"
            self.start_tcpdump(session, cmd_udp)
            self.start_tcpdump(session, cmd_gre)
    
    #end tcpdump_on_all_compute

    def tcpdump_stop_on_all_compute(self):
        sessions = {}
        for compute_ip in self.inputs.compute_ips:
            session = ssh(compute_ip,'root','c0ntrail123')
            self.stop_tcpdump(session)
    
    #end tcpdump_on_all_compute



    def tcpdump_analyze_on_compute(self, comp_ip, pcaptype):
        sessions = {}
        session = ssh(comp_ip,'root','c0ntrail123')
        self.logger.info("Analyzing on compute node %s" % comp_ip)
        if pcaptype=='UDP':
            pcaps1 = '/tmp/encap-udp.pcap'
            pcaps2 = '/tmp/encap-gre.pcap'
            cmd2='tcpdump  -r %s | grep UDP |wc -l' % pcaps1
            out2, err = execute_cmd_out(session, cmd2, self.logger)
            cmd3='tcpdump  -r %s | grep GRE | wc -l' % pcaps2
            out3, err = execute_cmd_out(session, cmd3, self.logger)
            count2 = int(out2.strip('\n'))
            count3 = int(out3.strip('\n'))
            if count2!=0 and count3 == 0:
                self.logger.info("%s UDP encapsulated packets are seen and %s GRE encapsulated packets are seen as expected" % (count2,count3))
                return True
            else:
                errmsg ="%s UDP encapsulated packets are seen and %s GRE encapsulated packets are seen.Not expected" % (count2,count3)
                self.logger.error(errmsg)
                assert False, errmsg
        elif pcaptype=='GRE':
            pcaps1 = '/tmp/encap-udp.pcap'
            pcaps2 = '/tmp/encap-gre.pcap'
            cmd2='tcpdump  -r %s | grep UDP |wc -l' % pcaps1
            out2, err = execute_cmd_out(session, cmd2, self.logger)
            cmd3='tcpdump  -r %s | grep GRE | wc -l' % pcaps2
            out3, err = execute_cmd_out(session, cmd3, self.logger)
            count2 = int(out2.strip('\n'))
            count3 = int(out3.strip('\n'))
            if count2==0 and count3 != 0:
                self.logger.info("%s GRE encapsulated packets are seen and %s UDP encapsulated packets are seen as expected" % (count3,count2))
                self.tcpdump_stop_on_all_compute()
                return True
            else:
                errmsg ="%s UDP encapsulated packets are seen and %s GRE encapsulated packets are seen.Not expected" % (count2,count3)
                self.logger.error(errmsg)
                self.tcpdump_stop_on_all_compute()
                assert False, errmsg

#       return True
    #end tcpdump_analyze_on_compute
########################################################################################################################################