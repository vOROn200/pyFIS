#!/usr/bin/env python3
"""Test MONO protocol query command."""

import argparse
import time
from lawo import SerialMONOMaster

def parse_args():
    parser = argparse.ArgumentParser(description="Test MONO query command")
    parser.add_argument("--port", default="COM3", help="Serial port")
    parser.add_argument("--baudrate", type=int, default=19200, help="Serial baudrate")
    parser.add_argument("--address", type=lambda v: int(v, 0), default=0x0,
                        help="MONO bus address (0x0 - 0xF)")
    parser.add_argument("--debug", action="store_true", help="Debug output")
    return parser.parse_args()

def print_reply(reply):
    if reply:
        print(f"Reply received: {' '.join(f'{b:02X}' for b in reply)}")
    else:
        print("No reply received")

# --- Полный список данных для вертикальной полосы ---
# В дампе: 18 пакетов для нечетных строк, 18 для четных.
# Каждый пакет данных (без адреса) содержит 32 байта.
# 0x90 (1001 0000) для нечетных, 0x10 (0001 0000) для четных.

# Функция-генератор сегментов данных для вертикальной полосы
def generate_vertical_line_data():
    """Генерирует адреса и 32-байтовые сегменты данных для вертикальной полосы."""
    # 32 байта данных, где только 4-й бит установлен (для 4-х модулей по 6 байт, и 2 байта на конце)
    # 0x90 = 1001 0000 (Вероятно, для нечетных строк)
    # 0x10 = 0001 0000 (Вероятно, для четных строк)

    data_pattern_odd = [
        0x90,0x00,0x00,0x00,0x00,0x00,  # 6 байт
        0x90,0x00,0x00,0x00,0x00,0x00,  # 6 байт
        0x90,0x00,0x00,0x00,0x00,0x00,  # 6 байт
        0x90,0x00,0x00,0x00,0x00,0x00,  # 6 байт
        0x90,0x00,0x00,0x00,0x00,0x00,  # 6 байт
        0x90,0x00                     # 2 байта. Итого 32 байта.
    ]

    # Исправляем паттерн, чтобы он точно соответствовал дампу (5x6 байт, 2 байта на конце).
    # В дампе 5x(0x90, 5x0x00) + (0x90, 5x0x00) = 6x(0x90, 5x0x00), что дает 36 байт,
    # НО в дампе только 32 байта данных. Возьмем 32 байта из дампа.
    # Реальный дамп: 5x(0x90, 5x0x00) + 2 последних байта = 32 байта
    # Нет, в дампе: 0xA1, 0x24, (32 байта данных), 0xEA, 0x7E
    
    # Пакет данных (32 байта) для нечетных строк (исключая 'засечки'):
    # 5 блоков по (0x90, 5x0x00) = 30 байт.
    # Оставшиеся 2 байта в дампе — это 0x00, 0x00
    # data = 5x[0x90,0x00,0x00,0x00,0x00,0x00] + [0x00,0x00] -> 32 байта
    
    # Паттерн, соответствующий большинству пакетов "полосы"
    base_data_odd = [0x90] + [0x00] * 5
    base_data_even = [0x10] + [0x00] * 5
    
    # 1. Нечетные строки (адреса от 0x24 до 0x13, всего 18 пакетов)
    for addr in range(0x24, 0x12, -1):
        # Если это адрес с "засечками", используем специальные данные
        if addr == 0x1C:
            data = [0x90, 0x7F, 0x3F, 0x00, 0x00, 0x00] + base_data_odd*4 + [0x00, 0x00]
        elif addr == 0x1B:
             # Это сложный пакет, который нужно точно скопировать
             data = [0x90,0x00,0x00,0x00,0x00,0x00,0x90,0x00,0x00,0x00,0x00,0x00,0x90,0x00,0x00,0x00,0x00,0x00,0x90,0x00,0x00,0x00,0xC0,0xDF,0x90,0x3C,0x7F,0x3F,0x7F,0x3F]
        else:
            # Базовый пакет вертикальной полосы
            data = base_data_odd*5 + [0x00, 0x00]
        
        # Корректировка: данные в дампе 0x1B и 0x1C длиннее, чем базовый шаблон
        # Убедимся, что все пакеты данных имеют одинаковую длину (32 байта в дампе).
        # Проверим длину: [0xA1, 0x24, DATA_32_BYTES, CS, 0x7E] -> 36 байт всего.
        # В дампе: 0xA1, 0x24, 32 байта данных, CS. ОК.
        
        # Упрощаем, используя базовый шаблон для всех, кроме тех, что с засечками
        if len(data) > 32: data = data[:32]
        
        yield addr, data

    # 2. Четные строки (адреса от 0x12 до 0x01, всего 18 пакетов)
    for addr in range(0x12, 0x00, -1):
        if addr == 0x0A:
            data = [0x10, 0x3F, 0x7F, 0x00, 0x00, 0x00] + base_data_even*4 + [0x00, 0x00]
        elif addr == 0x09:
            # Это сложный пакет, который нужно точно скопировать
            data = [0x10,0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0xC0,0xCF,0x10,0x7C,0x3F,0x7F,0x3F,0x7F]
        else:
            data = base_data_even*5 + [0x00, 0x00]
            
        if len(data) > 32: data = data[:32]
            
        yield addr, data

# Создаем сегмент данных, где все пиксели выключены (32 байта нулей)
CLEAN_DATA_SEGMENT = [0x00] * 32

def erase_display(master, address):
    print("\n--- Стирание данных дисплея (Запись нулей) ---")

    # Сначала отправляем команду настройки (CMD_PRE_BITMAP_FLIPDOT)
    setup_data = [0x24, 0x12] # Используем те же настройки, что и при рисовании
    master.send_command(address, master.CMD_PRE_BITMAP_FLIPDOT, setup_data)
    time.sleep(0.1)

    # Используем те же адреса, что и в функции generate_vertical_line_data()
    # Адреса: 0x24 до 0x01 (всего 36 сегментов)
    
    # Стирание нечетных строк (0x24 до 0x13)
    for addr in range(0x24, 0x12, -1):
        data = [addr] + CLEAN_DATA_SEGMENT
        master.send_command(address, master.CMD_COLUMN_DATA_FLIPDOT, data)
        # print(f"Стерт сегмент 0x{addr:02X}")
        time.sleep(0.01)

    # Стирание четных строк (0x12 до 0x01)
    for addr in range(0x12, 0x00, -1):
        data = [addr] + CLEAN_DATA_SEGMENT
        master.send_command(address, master.CMD_COLUMN_DATA_FLIPDOT, data)
        # print(f"Стерт сегмент 0x{addr:02X}")
        time.sleep(0.01)

    print("Данные успешно стерты со всех 36 сегментов.")

def main():
    args = parse_args()
    
    master = SerialMONOMaster(args.port, baudrate=args.baudrate, debug=args.debug)
    
    
    reply = master.send_command(args.address, master.CMD_QUERY, [0x7E])
    print_reply(reply)

    time.sleep(0.2)

    # Send query command and expect reply
    print(f"Querying display at address 0x{args.address:X}...")
    reply = master.send_command(args.address, master.CMD_QUERY, [])
    print_reply(reply)
    
    time.sleep(0.2)

    reply = master.send_command(args.address, master.CMD_PRE_BITMAP_FLIPDOT, [0x24 , 0x12])
    print_reply(reply)

    time.sleep(0.2)

    segment_count = 0
    for data_address, data_segment in generate_vertical_line_data():
        data = [data_address] + data_segment
        
        # CMD_COLUMN_DATA_FLIPDOT = 0xA1
        #reply = master.send_command(args.address, master.CMD_COLUMN_DATA_FLIPDOT, data)
        #print(f"Адрес 0x{data_address:02X} ({len(data)} байт). Ответ: ", end="")
        #print_reply(reply)
        
        segment_count += 1
        # Пауза между сегментами, чтобы дать дисплею время на обработку
        time.sleep(0.05) # Уменьшаем, чтобы ускорить, но можно увеличить, если есть ошибки

    print(f"\nПередано {segment_count} сегментов данных (0xA1).")

    #data_address = 0x24
    #data_segment =  [
    #    0x90,0x00,0x00,0x00,0x00,0x00,
    #    0x90,0x00,0x00,0x00,0x00,0x00,
    #    0x90,0x00,0x00,0x00,0x00,0x00,
    #    0x90,0x00,0x00,0x00,0x00,0x00,
    #    0x90,0x00,0x00,0x00,0x00,0x00]

    #data = [data_address] + data_segment

    #reply = master.send_command(args.address, master.CMD_COLUMN_DATA_FLIPDOT, data)
    #print_reply(reply)

    
    erase_display(master, args.address)
    time.sleep(0.2)

    reply = master.send_command(args.address, master.CMD_QUERY, [0x7E])
    print_reply(reply)
    
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
