"""
Copyright (C) 2020 Julian Metzler

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import serial

from .mono_protocol import MONOProtocol

class SerialMONOMaster(MONOProtocol):
    """
    A MONO bus master, sending and receiving frames using a serial port
    """
    
    def __init__(self, port, baudrate = 19200, bytesize = 8, parity = 'N',
                 stopbits = 1, timeout = 2.0, *args, **kwargs):
        """
        port:
        The serial port to use for communication
        """
        
        super().__init__(*args, **kwargs)
        
        if isinstance(port, serial.Serial):
            self.device = port
            self.port = self.device.port
        else:
            self.port = port
            self.device = serial.Serial(
                self.port,
                baudrate = baudrate,
                bytesize = bytesize,
                parity = parity,
                stopbits = stopbits,
                timeout = timeout
            )
    
    def _send(self, frame):
        """
        Actually send the frame.
        This varies depending on implementation
        """
        
        # Clear input buffer before sending to avoid reading stale data
        self.device.reset_input_buffer()
        self.device.write(frame)
    
    def _receive(self):
        """
        Actually receive data.
        Reads all available data from serial port.
        The data may contain echo of sent command followed by actual response.
        """
        
        import time
        
        # Wait a bit for response to arrive
        time.sleep(0.1)
        
        # Read all available data
        available = self.device.in_waiting
        if available > 0:
            data = self.device.read(available)
            
            # Parse frames from data
            frames = []
            current_frame = bytearray()
            in_frame = False
            
            for byte in data:
                if byte == 0x7E:
                    if in_frame:
                        # End of frame
                        current_frame.append(byte)
                        frames.append(bytes(current_frame))
                        current_frame = bytearray()
                        in_frame = False
                    else:
                        # Start of frame
                        current_frame = bytearray([byte])
                        in_frame = True
                else:
                    if in_frame:
                        current_frame.append(byte)
            
            # Return last complete frame (skip echo)
            if len(frames) >= 2:
                return frames[-1]
            elif frames:
                return frames[0]
        
        return bytes()


    def __del__(self):
        if hasattr(self, 'device'):
            self.device.close()
