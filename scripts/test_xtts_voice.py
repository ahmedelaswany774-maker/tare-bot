from pathlib import Path
from TTS.api import TTS

reference = Path('voice_reference.wav')
output = Path('voice_test_output.wav')
text = 'هذه عينة اختبار قصيرة بصوتي الحقيقي. إذا كان الصوت واضحًا ومطابقًا، سنستخدمه لاحقًا في إنتاج الحلقة الثانية.'

if not reference.exists():
    raise FileNotFoundError(reference)

print('Loading XTTS-v2 model...')
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('Generating voice sample...')
tts.tts_to_file(
    text=text,
    file_path=str(output),
    speaker_wav=str(reference),
    language='ar',
    split_sentences=False,
)
print(f'Generated {output}')
