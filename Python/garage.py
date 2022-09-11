import json
import binascii
import textwrap
from os.path import exists

import bitstring as bitstring
import numpy as np
import matplotlib.pyplot as plt
from rflib import *
from scipy.io import wavfile

_ONE = '1'
_ZERO = '0'

# APRIMATIC_TX2M_PARTIAL_BIT_RATE = 9600 / 6
# APRIMATIC_TX2M_PARTIAL_BIT_RATE = 600
# APRIMATIC_TX2M_PARTIAL_BIT_RATE = 48000
APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_READ = 29
#APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_SEND = 48
APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_SEND = 94
APRIMATIC_TX2M_FINAL_PARTIAL_BITS_READ = 8
#APRIMATIC_TX2M_FINAL_PARTIAL_BITS_SEND = 12
APRIMATIC_TX2M_FINAL_PARTIAL_BITS_SEND = 26
APRIMATIC_TX2M_BIT_RATE_READ = 600
APRIMATIC_TX2M_BIT_RATE_SEND = 595
APRIMATIC_TX2M_PARTIAL_BITS_PER_BIT_READ = 6
#APRIMATIC_TX2M_PARTIAL_BITS_PER_BIT_SEND = 10
APRIMATIC_TX2M_PARTIAL_BITS_PER_BIT_SEND = 20

APRIMATIC_TX2M_PARTIAL_BITS_FOR_ZERO_READ = '000011'
#APRIMATIC_TX2M_PARTIAL_BITS_FOR_ZERO_SEND = '0000000111'
APRIMATIC_TX2M_PARTIAL_BITS_FOR_ZERO_SEND = _ZERO * 14 + _ONE * 6

APRIMATIC_TX2M_PARTIAL_BITS_FOR_ONE_READ = '011111'
#APRIMATIC_TX2M_PARTIAL_BITS_FOR_ONE_SEND = '0011111111'
APRIMATIC_TX2M_PARTIAL_BITS_FOR_ONE_SEND = _ZERO * 4 + _ONE * 16

APRIMATIC_TX2M_PARTIAL_BIT_RATE_READ = APRIMATIC_TX2M_BIT_RATE_READ * APRIMATIC_TX2M_PARTIAL_BITS_PER_BIT_READ
APRIMATIC_TX2M_PARTIAL_BIT_RATE_SEND = APRIMATIC_TX2M_BIT_RATE_SEND * APRIMATIC_TX2M_PARTIAL_BITS_PER_BIT_SEND
APRIMATIC_TX2M_MESSAGE_BITS = 80
#APRIMATIC_TX2M_MODULATION_FREQUENCY = 433920000
APRIMATIC_TX2M_MODULATION_FREQUENCY = 433952000

_MY_DEBUG = False


# --

def get_stream_of_partial_bits_from_file(file_name):
    _BIAS = 2000
    LEFT_CHANNEL = 0
    RIGHT_CHANNEL = 1

    sample_rate, original_samples = wavfile.read(file_name)
    # print(f"number of channels = {original_samples.shape[RIGHT_CHANNEL]}")
    samples_per_bit = sample_rate / APRIMATIC_TX2M_PARTIAL_BIT_RATE_READ

    binary_samples = [_ONE if sample >= _BIAS else _ZERO for sample in original_samples[:, LEFT_CHANNEL]]

    if False:
        length = original_samples.shape[0] / sample_rate
        # print(f"length = {length}s")
        time = np.linspace(0., length, original_samples.shape[0])
        plt.plot(time, original_samples[:, 0], label="Left channel")
        # plt.plot(time, original_samples[:, 1], label="Right channel")
        plt.legend()
        plt.xlabel("Time [s]")
        plt.ylabel("Amplitude")
        print(f'{sample_rate=}; {APRIMATIC_TX2M_PARTIAL_BIT_RATE_READ=} => {samples_per_bit=}')
        print(original_samples.shape[0])
        print(type(original_samples.shape[0]))
        print(original_samples[:, 0])
        print(original_samples[:, 1])
        plt.show()
        plt.plot(time, binary_samples, label="Binary samples")
        plt.show()

    return binary_samples, samples_per_bit


# --

def get_stream_of_partial_bits_from_RF(d: RfCat):
    '''
    just sit and dump packets as they come in
    kinda like discover() but without changing any of the communications settings
    '''

    #d.RFxmit(b"\x5F\xBF\x23\xB4\xC3\xEB\xF3\xE5\x02\x98", repeat=7)
    # d.discover(length=240)
    # d.discover()
    print("Entering RFlisten mode...  packets arriving will be displayed on the screen")
    print("(press Enter to stop)")

    while not keystop():
        list_of_streams_of_partial_bits = []
        while True:
            try:
                # y, timestamp = d.RFrecv(blocksize=30)
                # print("(%5.3f) Received:  %s  | %s" % (timestamp, hexlify(y).decode(), makeFriendlyAscii(y)))
                y, timestamp = d.RFrecv(blocksize=240)
                yhex = binascii.hexlify(y).decode()
                # binary_string = binascii.unhexlify(yhex)
                stream_of_partial_bits = bin(int(yhex, 16))[2:]

                if could_be_part_of_valid_message(stream_of_partial_bits):
                    _MY_DEBUG and print("(%5.3f) received:  %s | %s" % (timestamp, yhex, stream_of_partial_bits))
                    print('.', end="")
                    list_of_streams_of_partial_bits.append(stream_of_partial_bits)
                else:
                    if len(list_of_streams_of_partial_bits) >= 6:
                        list_of_streams_of_partial_bits.append(stream_of_partial_bits)
                        break
                    else:
                        list_of_streams_of_partial_bits = [stream_of_partial_bits]
            except ChipconUsbTimeoutException:
                list_of_streams_of_partial_bits = []

        stream_of_partial_bits = ''.join(list_of_streams_of_partial_bits)

        return stream_of_partial_bits, timestamp


def could_be_part_of_valid_message(stream_of_partial_bits):
    count_1s = len([bit for bit in stream_of_partial_bits if bit == "1"])
    fraction_of_ones = count_1s / len(stream_of_partial_bits)
    if fraction_of_ones <= 0.8:
        return True
    else:
        return False


# --

def compute_clean_received_message(list_of_partial_bits):
    exact_expected_length = APRIMATIC_TX2M_MESSAGE_BITS * 2 + 2
    exact_length_simple_sequence_list = [simple_sequence for simple_sequence in list_of_partial_bits if len(simple_sequence) == exact_expected_length]

    if len(exact_length_simple_sequence_list) >= 3:
        remove_extreme_values = True
    elif len(exact_length_simple_sequence_list) > 1:
        remove_extreme_values = False
    elif len(exact_length_simple_sequence_list) == 1:
        return exact_length_simple_sequence_list[0]
    else:
        return None

    list_of_received_partial_bit_counts = []

    for pos in range(len(exact_length_simple_sequence_list[0])):
        minimum = exact_length_simple_sequence_list[0][pos]
        maximum = exact_length_simple_sequence_list[0][pos]
        sum = 0

        for sequence_number in range(len(exact_length_simple_sequence_list)):
            value = exact_length_simple_sequence_list[sequence_number][pos]
            sum += value
            if value > maximum:
                maximum = value
            if value < minimum:
                minimum = value
        if remove_extreme_values:
            sum -= maximum
            sum -= minimum
            average = sum / (len(exact_length_simple_sequence_list) - 2)
        else:
            average = sum / len(exact_length_simple_sequence_list)
        list_of_received_partial_bit_counts.append(average)

    if False:
        doubtful_samples = [value for value in list_of_received_partial_bit_counts if 0.3 <= value - round(value, 0) <= 0.7]
        print(f'{doubtful_samples=}')

        print(f'{list_of_received_partial_bit_counts=}')

    if False:
        received_bit_counts = [int(round(value, 0)) for value in list_of_received_partial_bit_counts]

    return list_of_received_partial_bit_counts

# --

def convert_partial_bit_list_to_message(list_of_received_partial_bit_counts):
    converted_bits = []

    if False and list_of_received_partial_bit_counts[0] >= 0.75 * APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_READ:
        converted_bits.append('<')
    res = list(zip(list_of_received_partial_bit_counts[1:], list_of_received_partial_bit_counts[2:]))
    res = [res[pos] for pos in range(len(res)) if pos % 2 == 0]
    # res = [(list_of_received_partial_bit_counts[pos], list_of_received_partial_bit_counts[pos+1]) for pos in range(len(list_of_received_partial_bit_counts)) if pos % 2 == 0]

    for pair in res:
        # if pair == (-4, 2):
        if -5.5 <= pair[0] <= -3 and 0.5 <= pair[1] <= 3:
            converted_bits.append('0')
        # elif pair == (-1, 5):
        elif -2 <= pair[0] <= -0.5 and 4 <= pair[1] <= 5.5:
            converted_bits.append('1')
        else:
            converted_bits.append('?')

    if False:
        converted_bits.append('>')

    return ''.join(converted_bits)


# --

def get_list_of_valid_messages(stream_of_partial_bits, samples_per_bit):
    _MY_DEBUG and print(f'{stream_of_partial_bits=}')

    stream_of_partial_bits = remove_micro_glitches(stream_of_partial_bits)

    _MY_DEBUG and print(f'{stream_of_partial_bits=}')

    sampled_lengths = convert_stream_of_partial_bits_to_sampled_lengths_list(stream_of_partial_bits)

    print(f'{sampled_lengths=}')

    if False and sampled_lengths[0] < -12.5 * samples_per_bit:
        sampled_lengths = sampled_lengths[1:]

    print(f'{sampled_lengths=}')

    # --

    if False:
        list_of_received_partial_bit_counts_1d = [round(sampled_length / samples_per_bit, 1) for sampled_length in sampled_lengths]
        print(f'{list_of_received_partial_bit_counts_1d=}')

    list_of_received_partial_bit_counts = [sampled_length / samples_per_bit for sampled_length in sampled_lengths]

    print(f'{list_of_received_partial_bit_counts=}')

    # --

    doubtful_samples = [value for value in list_of_received_partial_bit_counts if 0.4 <= value - round(value, 0) <= 0.7]
    print(f'{doubtful_samples=}')

    # --

    burst_list = []
    list_of_partial_bits = []
    simple_sequence = []

    for bit_count in list_of_received_partial_bit_counts:
        if abs(bit_count) >= 1.5 * APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_READ:
            simple_sequence.append(bit_count)
            list_of_partial_bits.append(simple_sequence)
            burst_list.append(list_of_partial_bits)
            list_of_partial_bits = []
            simple_sequence = [bit_count]
        else:
            if len(simple_sequence) > 0 and abs(bit_count) >= 0.75 * APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_READ:
                list_of_partial_bits.append(simple_sequence)
                simple_sequence = []

            simple_sequence.append(bit_count)

    if simple_sequence:
        list_of_partial_bits.append(simple_sequence)

    if list_of_partial_bits:
        burst_list.append(list_of_partial_bits)

    # --

    candidate_burst_list = []

    for list_of_partial_bits in burst_list:
        print('--------------')

        if len(list_of_partial_bits) <= 5:
            print(f'Discarding list of {len(list_of_partial_bits)} sequences of lengths {[len(simple_sequence) for simple_sequence in list_of_partial_bits]}')
        else:
            candidate_simple_sequence_list = []
            for simple_sequence in list_of_partial_bits:
                if 0.75 * 2 * APRIMATIC_TX2M_MESSAGE_BITS <= len(simple_sequence) <= 1.5 * 2 * APRIMATIC_TX2M_MESSAGE_BITS:
                    candidate_simple_sequence_list.append(simple_sequence)
                    print(f'{len(simple_sequence)} : {simple_sequence=}')
                else:
                    print(f'Discarding simple sequence of length {len(simple_sequence)}')
            if candidate_simple_sequence_list:
                candidate_burst_list.append(candidate_simple_sequence_list)

    # --

    list_of_received_valid_messages = []
    for list_of_partial_bits in candidate_burst_list:
        clean_partial_bits = compute_clean_received_message(list_of_partial_bits)

        list_of_received_repeated_instances = [convert_partial_bit_list_to_message(simple_sequence) for simple_sequence in list_of_partial_bits]

        if clean_partial_bits:
            clean_message = convert_partial_bit_list_to_message(clean_partial_bits)
            print(f'{len(clean_message)} : average {clean_message=}')

            for received_instance_message in list_of_received_repeated_instances:
                print(f'{"+" if received_instance_message == clean_message else "-"} {len(received_instance_message)} : candidate {received_instance_message=}')

            matching_received_messsages_count = len([received_instance_message for received_instance_message in list_of_received_repeated_instances if received_instance_message == clean_message])

            if matching_received_messsages_count >= 3:
                print('-----------------')
                print(f'+ valid {clean_message=}')
                list_of_received_valid_messages.append(clean_message)
            else:
                print('- rejected')
        else:
            print('No average')
            for received_instance_message in list_of_received_repeated_instances:
                print(f'* {len(received_instance_message)} : candidate {received_instance_message=}')

    return list_of_received_valid_messages


def convert_stream_of_partial_bits_to_sampled_lengths_list(stream_of_partial_bits):
    sampled_lengths = []
    current_value = stream_of_partial_bits[0]
    current_length = 0
    for bit_value in stream_of_partial_bits:
        if bit_value == current_value:
            current_length += 1
        else:
            sampled_lengths.append(current_length if current_value == _ONE else -current_length)
            current_value = bit_value
            current_length = 1
    # last sample
    sampled_lengths.append(current_length if current_value == _ONE else -current_length)
    return sampled_lengths


def remove_micro_glitches(stream_of_partial_bits):
    stream_of_partial_bits = ''.join([stream_of_partial_bits[0]] + [_ONE if stream_of_partial_bits[pos - 1] == _ONE and stream_of_partial_bits[pos + 1] == _ONE else stream_of_partial_bits[pos] for pos in range(1, len(stream_of_partial_bits) - 2)] + [stream_of_partial_bits[-1]])
    return stream_of_partial_bits


# --

def write_to_file(list_of_streams, samples_per_bit, timestamp, type, state):
    output_path = "/home/ochopelocho/PycharmProjects/TFG/Samples/JSON/"
    file_name = f'{output_path}/garage.{time.strftime("%Y-%m-%d")}.json'

    message_info = {  # stream, garage, timestamp, samples_per_bit, state in JSON
        "list_of_streams": list_of_streams,
        "samples_per_bit": samples_per_bit,
        "timestamp": timestamp,
        "type": type,
        "state": state
    }

    if exists(file_name):
        with open(file_name, "r") as log_file:
            messages_info_list = json.load(log_file)
    else:
        messages_info_list = []

    messages_info_list.append(message_info)

    with open(file_name, "w") as log_file:
        json.dump(messages_info_list, log_file, indent=4)

    return None

# --

def execute_read_messages():
    rfcat_samples_per_partial_bit = 3
    sample_rate = APRIMATIC_TX2M_PARTIAL_BIT_RATE_READ * rfcat_samples_per_partial_bit

    d = RfCat()
    d.setFreq(APRIMATIC_TX2M_MODULATION_FREQUENCY)
    d.setMdmModulation(MOD_ASK_OOK)
    d.setMdmDRate(sample_rate)
    d.setMaxPower()
    d.lowball()

    try:
        while True:
            stream_of_partial_bits, timestamp = get_stream_of_partial_bits_from_RF(d)
            samples_per_bit = rfcat_samples_per_partial_bit
            list_of_valid_messages = get_list_of_valid_messages(stream_of_partial_bits, samples_per_bit)

            if list_of_valid_messages:
                write_to_file(list_of_valid_messages, samples_per_bit, timestamp, "garage", "not used")

    except KeyboardInterrupt:
        d.setModeIDLE()
        print("Please press <enter> to stop")
        sys.stdin.read(1)
    except Exception as e:
        d.setModeIDLE()

# --

def convert_message_to_partial_bit_string_to_send(message: str):
    partial_bit_string = ''

    for bit in message:
        if bit == _ZERO:
            partial_bit_string += APRIMATIC_TX2M_PARTIAL_BITS_FOR_ZERO_SEND
        elif bit == _ONE:
            partial_bit_string += APRIMATIC_TX2M_PARTIAL_BITS_FOR_ONE_SEND

    return partial_bit_string

# --

def add_x(partial_bit_string):
    #partial_bit_string_hex = bytes('\\x' + '\\x'.join(binascii.hexlify(bytes(hex(int(partial_bit_string, base=2)), 'utf-8'), b':').decode('ascii').split(':')), 'utf-8')
    partial_bit_string_hex = bitstring.BitArray(bin=partial_bit_string).tobytes()

    # TODO: controlar el caso cuando al longitud de la cadena no sea multiplo de 8 bits
    #partial_bit_string_hex = '\\x'.join(textwrap.wrap(hex(int(partial_bit_string, base=2)),2))[2:]
    if False:
        pre_process = hex(int(partial_bit_string,2))[2:]
        partial_bit_string_hex = '\\x'+'\\x'.join(pre_process[i:i + 2] for i in range(0, len(pre_process), 2))

    return partial_bit_string_hex

# --

def execute_send_messages():
    #message = '11011111100101011001000010001111011111111101010101001100110110100101000101111110'
    #message = '00110000110011111010011010011101011100010010111111100101010000101010001010110010'
    message = '01100001000000000001110011110100010101100011001011101110101110110000000110010111'
    #message = '111111111111111011111111111111111111101110111111011111010111111111111111111111110111111111101111110111110101110111111111111111100011111010100100111111111111111110001111111011111111110110010111111111110101101111111110111111111110110111110110101111111111100011111111111111111111111111111111111111111111111011111011111111111111111111111111001001111111110011110111111111111011111111111111111111111111001111110111010011100111111101111111111111111111110111111111101011111111111011111100111100111111111111111111111111111101111011111111110111111111111111111111111111110111011111111111101111111111111111111111111110111111111101110111101111110111101111111110111101111111110111111111111111111111111011111011011111011111111111111111011111111111111111111111111110111111111101111100111111111111101111011111010100111111111011111101111111111111111111111111111111111111111111111111111110111011111111111111111111111101111111100001100111110111101111111111111011111111111111111111111111111111111011101111111111111111111111110011111111111111111111111111111111101011111110111111111111111111111111111111111111111111111111111111010111111111110111111111110101111111111111110111111111111111111110111111111111111111111011111111111111111111111011111111101111111011111111111111110111111111111111111111111111111111111111111111111101111111111111111101111111111111110010011010100010010011110110011101111010111111111011001100101111111111111011111111111111111110111010101111111111111111111111101110111101111111111111110111101111111111111111010111110111111111111110111111111111111111111111111111111111111111111111111111011111111111111110111111111111101111101111111111111111111110111111111111111111101111111111101111111101111010111111101111111111011011111111111111111111011111111111111010001011111111111111111111111111010101101101111001111111111110101011111111111111111111111111111111111111111111111100111101111111111110111011111111110011111111110111100100111111110101011011001111111011110111100111111110011110111111111111111011111111111100001111011111111100111111101111111111111111111111111110111111111111110111101101111111111111111111001101011111111111110111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000011111110000011111111111111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000000000000000011111110000000000000000111111110000011111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111111000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000011111110000000000000000011111110000000000000000111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111111000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000011111111111111111111000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111111000000000000000011111111000000000000000011111111000011111111111111111111000011111111111111111111000001111111111111111111000011111111111111111111000001111111111111111111000001111111111111111111000000000000000011111111000000000000000011111111000000000000000011111111000001111111111111111111000000000000000001111111000001111111111111111111000000000000000001111111000000000000000001111111000001111111111111110000011111111111111111110000011111111111111111110000000000000000011111111000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000011111111111111111111000000000000000011111111000011111111111111111111000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000011111110000000000000000111111110000000000000000011111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000011111111111111111111000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111111000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111100000111111111111111111110000000000000000111111110000111111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000011111111111111111111000000000000000011111111000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000011111110000000000000000111111110000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111111000000000000000011111111000011111111111111111110000000000000000011111110000011111111111111111110000000000000000011111110000000000000000111111110000000000000000011111110000000000000000011111111000000000000000011111111000000000000000011111111000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000011111110000000000000000011111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000111111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111111000011111111111111111111000011111111111111111111000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000111111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000000000000000011111110000000000000000111110000011111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111111000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000011111110000000000000000011111110000011111111111111111111000000000000000011111111000011111111111111111111000000000000000011111111000000000000000011111111000011111111111111111111000011111111111111111111000011111111111111111111000000000000000011111111000000000000000011111111000000000000000011111111000000000000000011111111000001111111111111111111000000000000000011111111000001111111111111111111000000000000000011111111000001111111111111111111000000000000000001111111000001111111111111111111000001111111111111111111000001111111111111111111000001111111111111111111000000000000000011111111000000000000000011111111000000000000000011111111000000000000000000000000000000011111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111000000000000000011111111000000000000000011111111000011111111111111111111000001111111111111111111000001111111111111111111000000000000000011111111000000000000000001111111000000000000000011111111000000000000000001111111000000000000000011111111000001111111111111111111000001111111111111111111000000000000000011111111000001111111111111111111000001111111111111111111000001111111111111111111100001111111111111111111100001111111111111111111000001111111111111111111000001111111111111111111000000000000000001111111000000000000000001111111000000000000000001111111000001111111111111111111100000000000000001111111100001111111111111111111100000000000000001111111100001111111111111111111100000000000000001111111100000000000000001111111100000000000000001111111100000000000000001111111100000000000000001111111100000000000000001111111100001111111111111111111100000111111111111111111100000000000000111111100000111111111111111111100000000000000001111111100000111111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000111111111111111111110000000000000000111111110000000000000000111111110000111111111111111111110000111111111111111111110000111111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000011111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000011111110000000000000000111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111110000000000000000111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000011111110000000000000000111111110000000000000000111111110000000000000000011111110000000000000000011111110000011111111111111111110000011111111111111111110000000000000000111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000000111111110000011111111111111111110000000000000000011111110000011111111111111111110000000000000000111111110000011111111111111111110000000000000000111111110000000000000000111111110000000000000111111100000000000000001111111110000000000000000111111110000000000000000111111110000111111111111111111100000111111111111111111100000000000000000111111100000111111111111111111100000000000000001111111100000111111111111111111100000000000000000111111100000000000000001111111100000000000000001111111100000111111111111111111100000000000000001111111100000000000000001111111100000111111111111111111100000111111111111111111100000111111111111111111100000111111111111111111100000111111111111111111100000111111111111111111100000000000000000111111100000000000000000111111100000000000000001111111100000111111111111111111100000000000000000111111100000111111111111111111100000000000000000111111100000000000000000111111100000111111111111111111100000111111111111111111100000111111111111111111100000000000000001111111100000000000000000111111100000000000000001111111100000000000000000111111100000111111111111111111100000000000000000111111100000111111111111111111100000000000000001111111100000111111111111111111110000000000000000111111110000111111111111111111100000111111111111111111100000111111111111111111100000111111111111111111100000000000000000111111100000000000000001111111100000000000000001111111100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000001000000000000000000100000000010010000101010000001001000001010000011111111111111110111111111111111110111011111011001010111111111111111101111111111101110110111011111111111111101111111111111111111111111111111011111111101111111111111111111111111111111111111111111111111111111100111011111111101101111111111111111111111110111111110110111111101111111111111011101100111111111101111111111111111111110011111111111111110101011111111101011111010111111101110111001111111111111111111111111111111111111111111111101111110111111111111011011111111111111111111111111111111111111111111111111110111111101011101110111111111111111111111111111111111111111110101101111111111111101111101111011111111111011111111111111111111111110101111111111010110111111111110111111111111101000111111101101011011111111110111111111111011111111111111111101111101111111110111111111111111111111111110101011011101001111011110011111111111111111111111111111110111111111111111111111111111111111111110111111101111111111111101011111111111111111111111111111111011100010111111111111111111111111111111111111111111110111011111111111111111111111011111110111111111111111111111111011110111111101111111111111111111110111111111111110111111111111110011101110111111111111111111111111111111111111111101111111111111111111111111111111111111111111111111111111110111111111111111111111111011111111111111111111111011101111111101111111111111111111111111100111111111101111111110111101110010111101111110101101111111111111111111110111101111111011111111111111111111111110111111101101111111011111111111111111111111111111111111111111011111111111111111111111111110111111111111111111111111011111111111011011101111111111111111111111111111111111110111111111111111110111111111111111111111110111111111111111111111111111111111101111111111111111111111101101111111111111111111111110111111101111111111110111111111111111111111111111101100111111101010111111111111111111111111111111111111011111111111111111111111111111111111111111111111111111111111110111111111110111110111111111'
    rfcat_samples_per_partial_bit = 1
    tx_rate = APRIMATIC_TX2M_PARTIAL_BIT_RATE_SEND * rfcat_samples_per_partial_bit

    d = RfCat()
    d.setFreq(APRIMATIC_TX2M_MODULATION_FREQUENCY)
    d.setMdmModulation(MOD_ASK_OOK)
    d.setMdmDRate(tx_rate)
    d.setMaxPower()
    d.lowball()

    partial_bit_string = convert_message_to_partial_bit_string_to_send(message)
    #partial_bit_string = message
    #print(partial_bit_string)
    # partial_bit_string_hex =  binascii.hexlify(bytes(partial_bit_string,'utf-8'))
    #partial_bit_string_hex = add_x((_ONE * (APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_SEND+3-16) ) + partial_bit_string + (_ZERO * APRIMATIC_TX2M_FINAL_PARTIAL_BITS_SEND) ) #bytes('\\x' + '\\x'.join(binascii.hexlify(bytes(hex(int(partial_bit_string, base=2)), 'utf-8'), b':').decode('ascii').split(':')), 'utf-8')
    partial_bit_string_hex = add_x((_ONE * (APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS_SEND)) + partial_bit_string + (_ZERO * APRIMATIC_TX2M_FINAL_PARTIAL_BITS_SEND)) #bytes('\\x' + '\\x'.join(binascii.hexlify(bytes(hex(int(partial_bit_string, base=2)), 'utf-8'), b':').decode('ascii').split(':')), 'utf-8')

    d.makePktFLEN(len(partial_bit_string_hex))

    #d.RFxmit(_ONE * (APRIMATIC_TX2M_PREAMBLE_PARTIAL_BITS - 6))
    #d.RFxmit(_ONE * 6 + partial_bit_string_hex + _ZERO * APRIMATIC_TX2M_FINAL_PARTIAL_BITS_SEND, repeat=7)
    #d.RFxmit(bytes(partial_bit_string_hex,'utf-8'))
    d.RFxmit(partial_bit_string_hex, repeat=6)
    if False:
        test_string_ff = (b'\xff') * 96
        test_string_00 = (b'\x00') * 96
        test_string_fa = (b'\x01\x23\x45\x67\x89\xab\xcd\xef') * 12
        #d.makePktFLEN(len(partial_bit_string_hex))
        d.makePktFLEN(len(test_string_ff))
        # d.RFxmit(b'\xff',repeat=10)
        # d.RFxmit(b'\x11',repeat=10)
        d.RFxmit(test_string_ff)
        d.RFxmit(test_string_00)
        d.RFxmit(test_string_fa)
        d.RFxmit(test_string_ff)

    d.setModeIDLE()

    # 369 para cualquier cadena, preambulo de 200 - preambulo normal, preambulo 29, mas cadena, mas 8 mini bits 0


# --

def main():
    #execute_read_messages()
    execute_send_messages()


# --

if __name__ == '__main__':
    main()