"""Policy config utilities."""

import random

import fixtures

from vnc_api.gen.resource_xsd import TimerType, SequenceType,\
                                                VirtualNetworkPolicyType


class AttachPolicyFixture(fixtures.Fixture):
    """Policy attach fixture to attach policy to Virtuak Networks."""
    def __init__(self, inputs, connections, vn_fixture, policy_fixture, policy_type=None):
        self.inputs = inputs
        self.logger = self.inputs.logger
        self.quantum_fixture= connections.quantum_fixture
        self.vnc_lib= connections.vnc_lib
        self.vn_fixture = vn_fixture
        self.policy_fixture = policy_fixture
        self.vn_obj = self.vnc_lib.virtual_network_read(fq_name_str=self.vn_fixture.vn_fq_name)
        self.policy_obj = self.vnc_lib.network_policy_read(fq_name=self.policy_fixture.policy_fq_name)
        seq = random.randint(1, 655535)
        kwargs = {'sequence' : SequenceType(seq, 0)}
        if policy_type == 'dynamic':
           kwargs.update({'timer' : TimerType()})
        self.policy_type = VirtualNetworkPolicyType(**kwargs)

    def setUp(self):
        self.logger.info("Attaching policy %s to vn %s",
                         self.policy_fixture.policy_name, self.vn_fixture.vn_name)
        super(AttachPolicyFixture, self).setUp()
        self.vn_obj.add_network_policy(self.policy_obj, self.policy_type)
        self.vnc_lib.virtual_network_update(self.vn_obj)
        #Required for verification by VNFixture in vn_test.py
        policy = self.quantum_fixture.get_policy_if_present(self.policy_fixture.project_name, self.policy_fixture.policy_name)
        policy_name_objs = dict((policy_obj['policy']['name'], policy_obj)
                                for policy_obj in self.vn_fixture.policy_objs)
        if policy['policy']['name'] not in policy_name_objs.keys():
            self.vn_fixture.policy_objs.append(policy)

    def cleanUp(self):
        self.logger.info("Dettaching policy %s from vn %s",
                         self.policy_fixture.policy_name, self.vn_fixture.vn_name)
        super(AttachPolicyFixture, self).cleanUp()
        self.vn_obj.del_network_policy(self.policy_obj)
        self.vnc_lib.virtual_network_update(self.vn_obj)
        #Required for verification by VNFixture in vn_test.py
        policy = self.quantum_fixture.get_policy_if_present(self.policy_fixture.project_name, self.policy_fixture.policy_name)
        policy_name_objs = dict((policy_obj['policy']['name'], policy_obj)
                                for policy_obj in self.vn_fixture.policy_objs)
        if policy['policy']['name'] in policy_name_objs.keys():
            self.vn_fixture.policy_objs.remove(policy_name_objs[policy['policy']['name']])