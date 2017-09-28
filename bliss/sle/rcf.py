import struct

import bliss.core.log

import common
import frames
from bliss.sle.pdu.rcf import *
from bliss.sle.pdu import rcf


class RCF(common.SLE):
    ''''''
    # TODO: Add error checking for actions based on current state

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self._service_type = 'rtnChFrames'
        self._version = kwargs.get('version', 5)

        self._handlers['RcfBindReturn'].append(self._bind_return_handler)
        self._handlers['RcfUnbindReturn'].append(self._unbind_return_handler)
        self._handlers['RcfStartReturn'].append(self._start_return_handler)
        self._handlers['RcfStopReturn'].append(self._stop_return_handler)
        self._handlers['RcfTransferBuffer'].append(self._data_transfer_handler)
        self._handlers['RcfScheduleStatusReportReturn'].append(self._schedule_status_report_return_handler)
        self._handlers['RcfStatusReportInvocation'].append(self._status_report_invoc_handler)
        self._handlers['RcfGetParameterReturn'].append(self._get_param_return_handler)
        self._handlers['AnnotatedFrame'].append(self._transfer_data_invoc_handler)
        self._handlers['SyncNotification'].append(self._sync_notify_handler)
        self._handlers['RcfPeerAbortInvocation'].append(self._peer_abort_handler)

    def bind(self, inst_id=None):
        ''''''
        pdu = RcfUsertoProviderPdu()['rcfBindInvocation']
        super(self.__class__, self).bind(pdu, inst_id=inst_id)

    def unbind(self, reason=0):
        ''''''
        pdu = RcfUsertoProviderPdu()['rcfUnbindInvocation']
        super(self.__class__, self).unbind(pdu, reason=reason)

    def get_parameter(self):
        ''''''
        #TODO: Implement get parameter
        pass

    def start(self, start_time, end_time, spacecraft_id, version, master_channel=False, virtual_channel=None):
        #TODO: Should likely move some of the attributes to optional config on __init__
        if not master_channel and not virtual_channel:
            err = (
                'Transfer start invocation requires a master channel or '
                'virtual channel from which to receive frames.'
            )
            raise AttributeError(err)

        start_invoc = RcfUsertoProviderPdu()

        if self._credentials:
            pass
        else:
            start_invoc['rcfStartInvocation']['invokerCredentials']['unused'] = None

        start_invoc['rcfStartInvocation']['invokeId'] = self.invoke_id
        start_time = struct.pack('!HIH', (start_time - common.CCSDS_EPOCH).days, 0, 0)
        stop_time = struct.pack('!HIH', (end_time - common.CCSDS_EPOCH).days, 0, 0)

        start_invoc['rcfStartInvocation']['startTime']['known']['ccsdsFormat'] = None
        start_invoc['rcfStartInvocation']['startTime']['known']['ccsdsFormat'] = start_time
        start_invoc['rcfStartInvocation']['stopTime']['known']['ccsdsFormat'] = None
        start_invoc['rcfStartInvocation']['stopTime']['known']['ccsdsFormat'] = stop_time

        req_gvcid = GvcId()
        req_gvcid['spacecraftId'] = spacecraft_id
        req_gvcid['versionNumber'] = version

        if master_channel:
            req_gvcid['vcId']['masterChannel'] = None
        else:
            req_gvcid['vcId']['virtualChannel'] = virtual_channel

        start_invoc['rcfStartInvocation']['requestedGvcId'] = req_gvcid

        bliss.core.log.info('Sending data start invocation ...')
        self.send(self.encode_pdu(start_invoc))

    def stop(self):
        pdu = RcfUsertoProviderPdu()['rcfStopInvocation']
        super(self.__class__, self).stop(pdu)

    def schedule_status_report(self, report_type='immediately', cycle=None):
        ''''''
        pdu = RcfUsertoProviderPdu()

        if self._credentials:
            pass
        else:
            pdu['rcfScheduleStatusReportInvocation']['invokerCredentials']['unused'] = None

        pdu['rcfScheduleStatusReportInvocation']['invokeId'] = self.invoke_id

        if report_type == 'immediately':
            pdu['rcfScheduleStatusReportInvocation']['reportType'][report_type] = None
        elif report_type == 'periodically':
            pdu['rcfScheduleStatusReportInvocation']['reportType'][report_type] = cycle
        elif report_type == 'stop':
            pdu['rcfScheduleStatusReportInvocation']['reportType'][report_type] = None
        else:
            raise ValueError('Unknown report type: {}'.format(report_type))

        bliss.core.log.info('Scheduling Status Report')
        self.send(self.encode_pdu(pdu))

    def peer_abort(self, reason=127):
        ''''''
        pdu = RcfUsertoProviderPdu()
        pdu['rcfPeerAbortInvocation'] = reason

        bliss.core.log.info('Sending Peer Abort')
        self.send(self.encode_pdu(pdu))
        self._state = 'unbound'

    def decode(self, message):
        ''''''
        return super(self.__class__, self).decode(message, RcfProvidertoUserPdu())

    def _handle_pdu(self, pdu):
        ''''''
        pdu_key = pdu.getName()
        pdu_key = pdu_key[:1].upper() + pdu_key[1:]
        if pdu_key in self._handlers:
            pdu_handlerss = self._handlers[pdu_key]
            for h in pdu_handlerss:
                h(pdu)
        else:
            err = (
                'PDU of type {} has no associated handlers. '
                'Unable to process further and skipping ...'
            )
            bliss.core.log.error(err.format(pdu_key))

    def _bind_return_handler(self, pdu):
        ''''''
        result = pdu['rcfBindReturn']['result']
        if 'positive' in result:
            bliss.core.log.info('Bind successful')
            self._state = 'ready'
        else:
            bliss.core.log.info('Bind unsuccessful: {}'.format(result['negative']))
            self._state = 'unbound'

    def _unbind_return_handler(self, pdu):
        ''''''
        result = pdu['rcfUnbindReturn']['result']
        if 'positive' in result:
            bliss.core.log.info('Unbind successful')
            self._state = 'unbound'
        else:
            bliss.core.log.error('Unbind failed. Treating connection as unbound')
            self._state = 'unbound'

    def _start_return_handler(self, pdu):
        ''''''
        result = pdu['rcfStartReturn']['result']
        if 'positiveResult' in result:
            bliss.core.log.info('Start successful')
            self._state = 'active'
        else:
            result = result['negativeResult']
            if 'common' in result:
                diag = result['common']
            else:
                diag = result['specific']
            bliss.core.log.info('Start unsuccessful: {}'.format(diag))
            self._state = 'ready'

    def _stop_return_handler(self, pdu):
        ''''''
        result = pdu['rcfStopReturn']['result']
        if 'positiveResult' in result:
            bliss.core.log.info('Stop successful')
            self._state = 'ready'
        else:
            bliss.core.log.info('Stop unsuccessful: {}'.format(result['negativeResult']))
            self._state = 'active'

    def _data_transfer_handler(self, pdu):
        ''''''
        self._handle_pdu(pdu['rcfTransferBuffer'][0])

    def _transfer_data_invoc_handler(self, pdu):
        ''''''
        frame = pdu.getComponent()
        if 'data' in frame and frame['data'].isValue:
            tm_data = frame['data'].asOctets()

        else:
            err = (
                'RcfTransferBuffer received but data cannot be located. '
                'Skipping further processing of this PDU ...'
            )
            bliss.core.log.info(err)
            return

        tmf = frames.TMTransFrame(tm_data)
        bliss.core.log.info('Sending {} bytes to telemetry port'.format(len(tmf._data[0])))
        self._telem_sock.sendto(tmf._data[0], ('localhost', 3076))

    def _sync_notify_handler(self, pdu):
        ''''''
        notification_name = pdu.getComponent()['notification'].getName()
        notification = pdu.getComponent()['notification'].getComponent()

        if notification_name == 'lossFrameSync':
            report = (
                'Frame Sync has been lost. See report below ... \n\n'
                'Lock Status Report\n'
                'Lock Time: {}\n'
                'Carrier Lock Status: {}\n'
                'Sub-Carrier Lock Status: {}\n'
                'Symbol Sync Lock Status: {}'
            ).format(
                notification['time'],
                notification['carrierLockStatus'],
                notification['subcarrierLockStatus'],
                notification['symbolSynclockStatus']
            )
        elif notification_name == 'productionStatusChange':
            prod_status_labels = ['running', 'interrupted', 'halted']
            report = 'Production Status Report: {}'.format(
                prod_status_labels[int(notification)]
            )
        elif notification_name == 'excessiveDataBacklog':
            report = 'Excessive Data Backlog Detected'
        elif notification_name == 'endOfData':
            report = 'End of Data Received'
        else:
            report = 'Received unknown sync notification: {}'.format(notification_name)

        bliss.core.log.info(report)

    def _schedule_status_report_return_handler(self, pdu):
        ''''''
        pdu = pdu['rcfScheduleStatusReportReturn']
        if pdu['result'].getName() == 'positiveResult':
            bliss.core.log.info('Status Report Scheduled Successfully')
        else:
            diag = pdu['result'].getComponent()

            if diag.getName() == 'common':
                diag_options = ['duplicateInvokeId', 'otherReason']
            else:
                diag_options = ['notSupportedInThisDeliveryMode', 'alreadyStopped', 'invalidReportingCycle']

            reason = diag_options[int(diag.getComponent())]
            bliss.core.log.warning('Status Report Scheduling Failed. Reason: {}'.format(reason))

    def _status_report_invoc_handler(self, pdu):
        ''''''
        pdu = pdu['rcfStatusReportInvocation']
        report = 'Status Report\n'
        report += 'Number of Error Free Frames: {}\n'.format(pdu['errorFreeFrameNumber'])
        report += 'Number of Delivered Frames: {}\n'.format(pdu['deliveredFrameNumber'])

        frame_lock_status = ['In Lock', 'Out of Lock', 'Unknown']
        report += 'Frame Sync Lock Status: {}\n'.format(frame_lock_status[pdu['frameSyncLockStatus']])

        symbol_lock_status = ['In Lock', 'Out of Lock', 'Unknown']
        report += 'Symbol Sync Lock Status: {}\n'.format(symbol_lock_status[pdu['symbolSyncLockStatus']])

        lock_status = ['In Lock', 'Out of Lock', 'Not In Use', 'Unknown']
        report += 'Subcarrier Lock Status: {}\n'.format(lock_status[pdu['subcarrierLockStatus']])

        carrier_lock_status = ['In Lock', 'Out of Lock', 'Unknown']
        report += 'Carrier Lock Status: {}\n'.format(lock_status[pdu['carrierLockStatus']])

        production_status = ['Running', 'Interrupted', 'Halted']
        report += 'Production Status: {}'.format(production_status[pdu['productionStatus']])

        bliss.core.log.warning(report)

    def _get_param_return_handler(self, pdu):
        ''''''
        pdu = pdu['rcfGetParameterReturn']
        #TODO: Implement

    def _peer_abort_handler(self, pdu):
        ''''''
        pdu = pdu['rcfPeerAbortInvocation']
        opts = [
            'accessDenied', 'unexpectedResponderId', 'operationalRequirement',
            'protocolError', 'communicationsFailure', 'encodingError', 'returnTimeout',
            'endOfServiceProvisionPeriod', 'unsolicitedInvokeId', 'otherReason'
        ]
        bliss.core.log.error('Peer Abort Received. {}'.format(opts[pdu]))
        self._state = 'unbound'
        self.disconnect()
