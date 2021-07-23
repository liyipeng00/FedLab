import numpy as np

import torch
import torch.distributed as dist
from fedlab_core.communicator import package as config
from fedlab_core.communicator.package import Package


class PackageProcessor(object):
    """Provide more flexible distributed tensor communication functions based on :func:`torch.distributed.send` and
    :func:`torch.distributed.recv`
    
    Notes:
        EVERYTHING is Tensor in FedLab.
    """
    @staticmethod
    def recv_package(src=None):
        """Two-segment tensor communication pattern based on ``torch.distributed``

        Pattern is shown as follows:
            1.1 sender: send a header tensor containing ``content_size`` to receiver
            1.2 receiver: receive the header, and get the value of ``content_size`` and create a buffer for incoming content

            2.1 sender: send a content tensor composed of a list of tensors and their offsets
            2.2 receiver: receive the content tensor, and parse it to obtain a tensor list using parser function
        """
        def recv_header(src=src, parse=True):
            buffer = torch.zeros(size=(config.HEADER_SIZE, ))
            dist.recv(buffer, src=src)
            if parse is True:
                return Package.parse_header(buffer)
            else:
                return buffer

        def recv_slices(slices_size, src):
            buffer_slices = torch.zeros(size=(slices_size, ),
                                        dtype=torch.int32)
            dist.recv(buffer_slices, src=src)
            slices = [x.item() for x in buffer_slices]
            return slices

        def recv_content(slices, src):
            content_size = sum(slices)
            buffer = torch.zeros(size=(content_size, ))
            dist.recv(buffer, src=src)
            return Package.parse_content(slices, buffer)

        sender_rank, _, slices_size, message_code = recv_header(src=src)
        # 收到第一段包，第二段包指定来源rank
        if slices_size > 0:
            slices = recv_slices(slices_size=slices_size, src=sender_rank)
            content = recv_content(slices, src=sender_rank)
        else:
            content = None

        return sender_rank, message_code, content

    @staticmethod
    def send_package(package, dst):
        """Two-segment tensor communication pattern based on ``torch.distributed``

        Pattern is shown as follows:
            1.1 sender: send a header tensor containing ``content_size`` to receiver
            1.2 receiver: receive the header, and get the value of ``content_size`` and create a buffer for incoming content

            2.1 sender: send a content tensor composed of a list of tensors and their offsets
            2.2 receiver: receive the content tensor, and parse it to obtain a tensor list using parser function
        """
        def send_header(header, dst):
            header[config.HEADER_RECEIVER_RANK_IDX] = dst
            dist.send(header, dst=dst)

        def send_slices(slices, dst):
            np_slices = np.array(slices, dtype=np.int32)
            tensor_slices = torch.from_numpy(np_slices)
            dist.send(tensor_slices, dst=dst)

        def send_content(content, dst):
            dist.send(content, dst=dst)

        send_header(header=package.header, dst=dst)

        if package.header[config.HEADER_SLICE_SIZE_IDX] > 0:
            send_slices(slices=package.slices, dst=dst)

            send_content(content=package.content, dst=dst)
