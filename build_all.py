#!/usr/bin/env python3
"""Rebuild every StarDict dictionary in stardict/ from the apple-peeler XML in output/.

Usage: build_all.py [BASENAME ...]   (no arguments = build everything)
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

# (basename, source XML name, display name, id regex or None)
# Bilingual dictionaries are split by direction: the letter before "_" in an entry id is its
# source language (e_ = English).
BILINGUAL = [
    # code, language, XML name, source-language id letter, title
    ('FR', 'French', 'French - English', 'f', 'Oxford-Hachette'),
    ('HR', 'Croatian', 'Croatian - English', 'h', 'Praktický Anglicko-Chorvatský Slovník'),
    ('CS', 'Czech', 'Czech - English', 'c', 'Velký anglicko-český a česko-anglický slovník'),
    ('DA', 'Danish', 'Danish - English', 'd', 'Praktisk Engelsk-Dansk Ordbog'),
    ('NL', 'Dutch', 'Dutch - English', 'n', 'Prisma Handwoordenboek Engels'),
    ('FI', 'Finnish', 'Finnish - English', 'f', 'MOT sanakirja'),
    ('DE', 'German', 'German - English', 'd', 'Oxford German Dictionary'),
    ('EL', 'Greek', 'Greek - English', 'g', 'Stavropoulos Oxford Greek-English Learners Dictionary'),
    ('HU', 'Hungarian', 'Hungarian - English', 'h', 'Magay Tamás szótár'),
    ('IT', 'Italian', 'Italian - English', 'i', 'Oxford Paravia Il Dizionario'),
    ('NO', 'Norwegian', 'Norwegian - English', 'n', 'Engelsk Ordbok'),
    ('PL', 'Polish', 'Polish - English', 'p', 'Oxford PWN Polish-English Dictionary'),
    ('PT', 'Portuguese', 'Portuguese - English', 'p', 'Oxford Portuguese Dictionary'),
    ('RU', 'Russian', 'Russian - English', 'r', 'Oxford Russian Dictionary'),
    ('SK', 'Slovak', 'Slovak - English', 's', 'Veľký Anglicko-Slovenský Slovník'),
    ('ES', 'Spanish', 'Spanish - English', 's', 'Gran Diccionario Oxford'),
    ('SV', 'Swedish', 'Swedish - English', 's', 'NE Professional English-Swedish / Svensk-Engelska'),
    ('UK', 'Ukrainian', 'Ukrainian - English', 'u', 'Українсько-Англійський Словник'),
    ('AR', 'Arabic', 'Arabic - English', 'a', 'Oxford Arabic Dictionary'),
    ('TR', 'Turkish', 'Turkish - English', 't', 'Oxford Turkish Dictionary'),
    ('BN', 'Bengali', 'Bangla - English', 'b', 'Oxford Bengali Dictionaries'),
    ('GU', 'Gujarati', 'Gujarati - English', 'g', 'Oxford Gujarati Dictionaries'),
    ('HI', 'Hindi', 'Hindi - English', 'h', 'Oxford Hindi Dictionaries'),
    ('KN', 'Kannada', 'Kannada - English', 'k', 'Oxford Kannada Dictionaries'),
    ('ML', 'Malayalam', 'Malayalam - English', 'm', 'Oxford Malayalam Dictionaries'),
    ('PA', 'Punjabi', 'Punjabi - English', 'p', 'Oxford Punjabi Dictionaries'),
    ('TA', 'Tamil', 'Tamil - English', 't', 'Oxford Tamil Dictionaries'),
    ('TE', 'Telugu', 'Telugu - English', 't', 'Oxford Telugu Dictionaries'),
    ('UR', 'Urdu', 'Urdu - English', 'u', 'Oxford Urdu Dictionaries'),
    ('ID', 'Indonesian', 'Indonesian - English', 'i', 'Oxford Study Indonesian Dictionary'),
    ('KK', 'Kazakh', 'Kazakh - English', 'k', 'Оксфорд Қазақ Cөздігі'),
    ('MS', 'Malay', 'Malay - English', 'm', 'Kamus Dwibahasa Oxford Fajar'),
    ('TH', 'Thai', 'Thai - English', 't', 'พจนานุกรมอังกฤษ-ไทย & ไทย-อังกฤษ'),
    ('VI', 'Vietnamese', 'Vietnamese - English', 'v', 'Từ điển Lạc Việt'),
    ('ZHS', 'Chinese (Simplified)', 'Simplified Chinese - English', 'z', '牛津英汉汉英词典'),
    ('ZHT', 'Chinese (Traditional)', 'Traditional Chinese - English', 'z', '譯典通英漢雙向字典'),
    ('YUE', 'Cantonese', 'Cantonese - English Oxford', 'y', '牛津粵英雙語詞典'),
    ('KO', 'Korean', 'Korean - English', 'k', '뉴에이스 영한사전 / 한영사전'),
]

DICTS = [
    ('NOAD', 'New Oxford American Dictionary', 'New Oxford American Dictionary', None),
    ('ODE', 'Oxford Dictionary of English', 'Oxford Dictionary of English', None),
    ('OAWT', "Oxford American Writer's Thesaurus", "Oxford American Writer's Thesaurus", None),
    ('OTE', 'Oxford Thesaurus of English', 'Oxford Thesaurus of English', None),
    # output/Apple Dictionary.xml comes from prep_apple_dictionary.py, not apple-peeler
    ('APPLE', 'Apple Dictionary', 'Apple Dictionary', None),
    # Single-language
    ('BG', 'Bulgarian', 'Bulgarian: Тълковен речник на съвременния български език', None),
    ('CA', 'Catalan', 'Catalan: Larousse Diccionari Manual de la llengua catalana', None),
    ('HR', 'Croatian', 'Croatian: Hrvatski Enciklopedijski Rječnik', None),
    ('DA', 'Danish', 'Danish: Politikens Nudansk Ordbog', None),
    ('NL', 'Dutch', 'Dutch: Prisma woordenboek Nederlands', None),
    ('FR', 'French', 'French: Multidictionnaire de la langue française', None),
    ('DE', 'Duden Dictionary Data Set I', 'German: Duden-Wissensnetz deutsche Sprache', None),
    ('EL', 'Greek', 'Greek: Λεξικό της κοινής νεοελληνικής', None),
    ('IT', 'Italian', 'Italian: Dizionario italiano', None),
    ('NO', 'Norwegian', 'Norwegian: Norsk Ordbok', None),
    ('PL', 'Polish', 'Polish: Uniwersalny słownik języka polskiego', None),
    ('PT', 'Portuguese', 'Portuguese: Dicionário de Português', None),
    ('RO', 'Romanian', 'Romanian: Dicţionarul explicativ al limbii române', None),
    ('RU', 'Russian', 'Russian: Толковый словарь русского языка', None),
    ('ES', 'Spanish', 'Spanish: Larousse Diccionario General de la Lengua Española', None),
    ('SV', 'Swedish', 'Swedish: NE Ordbok', None),
    # French - German has no English side: f_ = French->German, d_ = German->French
    ('FR-DE', 'French - German', 'French → German: PONS Großwörterbuch', '^f_'),
    ('DE-FR', 'French - German', 'German → French: PONS Großwörterbuch', '^d_'),
    # Asian and Middle Eastern single-language and single-direction dictionaries
    ('HE', 'Hebrew', 'Hebrew: מילון אבן-שושן', None),
    ('TR', 'Turkish', 'Turkish: Arkadaş Türkçe Sözlük', None),
    ('HI', 'Hindi', 'Hindi: राजपाल हिन्दी शब्दकोश', None),
    ('MS', 'Malay', 'Malay: Kamus Komprehensif Bahasa Melayu', None),
    ('TH', 'Thai', 'Thai: พจนานุกรมไทย', None),
    ('KO', 'Korean', 'Korean: 뉴에이스 국어사전', None),
    ('JA', 'Sanseido Super Daijirin', 'Japanese: スーパー大辞林', None),
    ('ZHS', 'The Standard Dictionary of Contemporary Chinese', 'Chinese (Simplified): 现代汉语规范词典', None),
    ('ZHS-IDIOMS', 'Simplified Chinese Idioms', 'Chinese (Simplified) Idioms: 汉语成语词典', None),
    ('ZHS-THES', 'Simplified Chinese Thesaurus', 'Chinese (Simplified) Thesaurus: 现代汉语同义词典', None),
    ('ZHT', 'Traditional Chinese', 'Chinese (Traditional): 五南國語活用辭典', None),
    ('ZHT-COMMON', 'Traditional Chinese Common Words', 'Chinese (Traditional) Common Words: 商務新詞典', None),
    ('ZHT-EN-IDIOMS', 'Traditional Chinese - English Idioms', 'Chinese (Traditional) → English Idioms: 漢英對照成語詞典', None),
    ('YUE-EN-COLLOQ', 'Cantonese - English Colloquialisms', 'Cantonese → English Colloquialisms: 英譯廣東口語詞典', None),
    # Bilingual pairs without English or with non-letter id prefixes
    ('ZHS-JA', 'Simplified Chinese - Japanese', 'Chinese (Simplified) → Japanese: 超級クラウン中日辞典', '^z_'),
    ('JA-ZHS', 'Simplified Chinese - Japanese', 'Japanese → Chinese (Simplified): クラウン日中辞典', '^j_'),
    ('EN-JA', 'Sanseido The WISDOM English-Japanese Japanese-English Dictionary', 'English → Japanese: ウィズダム英和辞典', '^WDEJ'),
    ('JA-EN', 'Sanseido The WISDOM English-Japanese Japanese-English Dictionary', 'Japanese → English: ウィズダム和英辞典', '^WDJE'),
]
for code, lang, xml, letter, title in BILINGUAL:
    DICTS.append((f'{code}-EN', xml, f'{lang} → English: {title}', f'^{letter}_'))
    DICTS.append((f'EN-{code}', xml, f'English → {lang}: {title}', '^e_'))


# Headwords marked with pronunciation hints that books don't print; they're also indexed without
# these combining marks. (Vietnamese uses the same dot below as a real tone mark, so this is
# per dictionary, never global.)
UNMARK = {
    'EN-KO': '́̀',  # stress accents on English headwords: abstráctor, bóxing rìng
    'DE-FR': '̣̱',  # PONS stress dots/lines under German vowels: Ạnschluss, a̱ß
}


def main():
    wanted = set(sys.argv[1:])
    for base, xml, name, ids in DICTS:
        unmark = UNMARK.get(base)
        if wanted and base not in wanted:
            continue
        cmd = [sys.executable, str(HERE / 'to_stardict.py'), str(HERE / 'output' / f'{xml}.xml'),
               str(HERE / 'stardict'), base, '--bookname', name]
        if ids:
            cmd += ['--ids', ids]
        if unmark:
            cmd += ['--unmark', unmark]
        out = subprocess.run(cmd, capture_output=True, text=True)
        last = (out.stdout.strip().splitlines() or [''])[-1]
        print(f'{base:7} {last if out.returncode == 0 else "FAILED: " + out.stderr.strip()[-300:]}', flush=True)


if __name__ == '__main__':
    main()
