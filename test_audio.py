# test_audio.py
import sys
import os
sys.path.append('backend')

from audio_editor import AudioEditor

def test_audio_functionality():
    editor = AudioEditor()
    
    # Тестируем базовые функции
    print("Testing audio editor...")
    
    # Создаем тестовый файл (если есть)
    test_files = [f for f in os.listdir('.') if f.endswith('.mp3')]
    
    if test_files:
        test_file = test_files[0]
        print(f"Testing with: {test_file}")
        
        # Длительность
        duration = editor.get_audio_duration(test_file)
        print(f"Duration: {duration} seconds")
        
        # Waveform
        waveform = editor.generate_waveform(test_file)
        if waveform:
            print("Waveform generated successfully")
        else:
            print("Waveform generation failed")
        
        # Рекомендация отрезка
        segment = editor.suggest_best_segment(test_file)
        print(f"Suggested segment start: {segment}")
    else:
        print("No MP3 files found for testing")

if __name__ == "__main__":
    test_audio_functionality()
