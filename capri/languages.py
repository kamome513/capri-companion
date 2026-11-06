"""The languages she can hear, understand and speak: the 25 that NVIDIA's Parakeet v3 speech model hears.

* Hearing: "Hey Capri" is still caught by her small always-on ears (it's a name, it sounds the same in every
  language); what you say after it is heard by Parakeet v3 (about 650 MB, downloaded once, runs offline).
* Understanding: the everyday commands (open, close, play, pause, next, louder, quieter, what time is it...)
  work in every one of these languages by themselves. Anything else goes to your AI, which understands them all.
* Speaking: her own neural voice speaks all of them, with each language's pronunciation (since 2.3.2); without
  it, a Windows voice for that language if you have one installed, else espeak-ng. ElevenLabs and Fish Audio
  speak them all. "Keep her voice" leaves your voice as it is. Your AI answers in your language, and her own built-in lines are translated
  by your AI once and remembered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str            # ISO 639-1
    name: str            # in English
    native: str          # in itself
    espeak: str          # espeak-ng voice
    kokoro: tuple[str, str] | None = None     # (Kokoro's own speaker, its language code) for its accent, if Kokoro has one


LANGUAGES: dict[str, Language] = {l.code: l for l in (
    Language("en", "English", "English", "en"),
    Language("bg", "Bulgarian", "Български", "bg"),
    Language("hr", "Croatian", "Hrvatski", "hr"),
    Language("cs", "Czech", "Čeština", "cs"),
    Language("da", "Danish", "Dansk", "da"),
    Language("nl", "Dutch", "Nederlands", "nl"),
    Language("et", "Estonian", "Eesti", "et"),
    Language("fi", "Finnish", "Suomi", "fi"),
    Language("fr", "French", "Français", "fr", ("ff_siwis", "fr-fr")),
    Language("de", "German", "Deutsch", "de"),
    Language("el", "Greek", "Ελληνικά", "el"),
    Language("hu", "Hungarian", "Magyar", "hu"),
    Language("it", "Italian", "Italiano", "it", ("if_sara", "it")),
    Language("lv", "Latvian", "Latviešu", "lv"),
    Language("lt", "Lithuanian", "Lietuvių", "lt"),
    Language("mt", "Maltese", "Malti", "mt"),
    Language("pl", "Polish", "Polski", "pl"),
    Language("pt", "Portuguese", "Português", "pt", ("pf_dora", "pt-br")),
    Language("ro", "Romanian", "Română", "ro"),
    Language("ru", "Russian", "Русский", "ru"),
    Language("sk", "Slovak", "Slovenčina", "sk"),
    Language("sl", "Slovenian", "Slovenščina", "sl"),
    Language("es", "Spanish", "Español", "es", ("ef_dora", "es")),
    Language("sv", "Swedish", "Svenska", "sv"),
    Language("uk", "Ukrainian", "Українська", "uk"),
)}

# A spoken cue before each command (made on your PC by espeak-ng, never sent anywhere): Parakeet v3 works out the
# language by itself, and a two-word command isn't enough for it to tell - it guesses English. With a couple of
# sentences in your language first it knows, and only what you said after the cue is kept.
CUES = {
    "bg": "Това е изречение на български. Сега говоря с теб на български, за да познаеш езика.",
    "hr": "Ovo je rečenica na hrvatskom. Sada razgovaram s tobom na hrvatskom, da prepoznaš jezik.",
    "cs": "Toto je věta v češtině. Teď s tebou mluvím česky, abys poznal jazyk.",
    "da": "Dette er en sætning på dansk. Jeg taler dansk med dig nu, så du kan genkende sproget.",
    "nl": "Dit is een zin in het Nederlands. Ik praat nu Nederlands met je, zodat je de taal herkent.",
    "et": "See on lause eesti keeles. Ma räägin sinuga nüüd eesti keeles, et sa keele ära tunneksid.",
    "fi": "Tämä on lause suomeksi. Puhun nyt kanssasi suomea, jotta tunnistat kielen.",
    "fr": "Ceci est une phrase en français. Je te parle maintenant en français, pour que tu reconnaisses la langue.",
    "de": "Das ist ein Satz auf Deutsch. Ich spreche jetzt Deutsch mit dir, damit du die Sprache erkennst.",
    "el": "Αυτή είναι μια πρόταση στα ελληνικά. Σου μιλάω τώρα ελληνικά, για να αναγνωρίσεις τη γλώσσα.",
    "hu": "Ez egy magyar mondat. Most magyarul beszélek veled, hogy felismerd a nyelvet.",
    "it": "Questa è una frase in italiano. Ora ti parlo in italiano, così riconosci la lingua.",
    "lv": "Šis ir teikums latviešu valodā. Tagad es runāju ar tevi latviski, lai tu atpazītu valodu.",
    "lt": "Tai sakinys lietuvių kalba. Dabar kalbu su tavimi lietuviškai, kad atpažintum kalbą.",
    "mt": "Din hija sentenza bil-Malti. Issa qed nitkellem miegħek bil-Malti, biex tagħraf il-lingwa.",
    "pl": "To jest zdanie po polsku. Teraz mówię do ciebie po polsku, żebyś rozpoznał język.",
    "pt": "Esta é uma frase em português. Agora estou a falar contigo em português, para reconheceres a língua.",
    "ro": "Aceasta este o propoziție în limba română. Acum vorbesc cu tine în română, ca să recunoști limba.",
    "ru": "Это предложение на русском языке. Я говорю с тобой по-русски, чтобы ты узнал язык.",
    "sk": "Toto je veta v slovenčine. Teraz s tebou hovorím po slovensky, aby si spoznal jazyk.",
    "sl": "To je stavek v slovenščini. Zdaj govorim s tabo slovensko, da prepoznaš jezik.",
    "es": "Esta es una frase en español. Ahora te hablo en español, para que reconozcas el idioma.",
    "sv": "Det här är en mening på svenska. Jag pratar svenska med dig nu, så att du känner igen språket.",
    "uk": "Це речення українською мовою. Я зараз говорю з тобою українською, щоб ти впізнав мову.",
}

_current = "en"
keep_voice = False       # Settings: keep her voice in any language (even one it can't pronounce)


def set_current(code: str) -> str:
    """The language she's using now (Settings -> Wake word -> Language). Unknown -> English."""
    global _current
    _current = code if code in LANGUAGES else "en"
    return _current


def current() -> str:
    return _current


def get(code: str | None = None) -> Language:
    return LANGUAGES.get(code or _current, LANGUAGES["en"])


def english() -> bool:
    return _current == "en"


def find(said: str) -> str:
    """'german' / 'deutsch' / 'Deutsch' -> 'de' ('' if it isn't one of hers)."""
    s = (said or "").strip().lower()
    for lang in LANGUAGES.values():
        if s in (lang.code, lang.name.lower(), lang.native.lower()):
            return lang.code
    return ""


# -- the everyday commands in every language --------------------------------------------------------------------
# Each language: (its words, the English command words they mean). Matched as whole words at the start of what
# you said, after lowercasing - so "öffne Discord" -> "open discord", "mets pause" -> "pause the music".
# Only the start of the sentence is swapped; app names and songs are left exactly as you said them.
_C = {
    "open": "open", "close": "close", "play": "play", "pause": "pause the music", "resume": "resume the music",
    "next": "next song", "previous": "previous song", "louder": "turn it up", "quieter": "turn it down",
    "time": "what time is it", "weather": "whats the weather", "screenshot": "take a screenshot",
    "minimize": "minimise everything", "stop": "stop", "mute": "mute discord", "unmute": "unmute discord",
}
COMMANDS: dict[str, list[tuple[str, str]]] = {
    "de": [("öffne|öffnen|starte|starten|mach auf", "open"), ("schließe|schließen|schliesse|beende|beenden", "close"),
           ("spiele|spiel|abspielen", "play"), ("pause|pausieren|anhalten", "pause"),
           ("weiter|fortsetzen", "resume"), ("nächstes lied|nächster song|nächstes|weiterschalten", "next"),
           ("vorheriges lied|zurück|vorheriges", "previous"), ("lauter", "louder"), ("leiser", "quieter"),
           ("wie spät ist es|wie viel uhr ist es|uhrzeit", "time"), ("wie ist das wetter|wetter", "weather"),
           ("mach einen screenshot|bildschirmfoto|screenshot", "screenshot"),
           ("alles minimieren|minimiere alles", "minimize"), ("stummschalten|stumm", "mute")],
    "fr": [("ouvre|ouvrir|lance|lancer|démarre", "open"), ("ferme|fermer|quitte|quitter", "close"),
           ("joue|jouer|mets|mettre", "play"), ("pause|mets en pause", "pause"), ("reprends|reprendre", "resume"),
           ("chanson suivante|suivant|suivante", "next"), ("chanson précédente|précédent|précédente", "previous"),
           ("plus fort|monte le son", "louder"), ("moins fort|baisse le son", "quieter"),
           ("quelle heure est il|quelle heure", "time"), ("quel temps fait il|météo", "weather"),
           ("fais une capture d écran|capture d écran", "screenshot"), ("réduis tout|tout réduire", "minimize"),
           ("coupe le micro|muet", "mute")],
    "es": [("abre|abrir|inicia|iniciar|lanza", "open"), ("cierra|cerrar|sal de", "close"),
           ("reproduce|reproducir|pon|toca", "play"), ("pausa|pausar", "pause"), ("continúa|reanuda|sigue", "resume"),
           ("siguiente canción|siguiente", "next"), ("canción anterior|anterior", "previous"),
           ("más alto|sube el volumen", "louder"), ("más bajo|baja el volumen", "quieter"),
           ("qué hora es|que hora es", "time"), ("qué tiempo hace|el clima|el tiempo", "weather"),
           ("haz una captura de pantalla|captura de pantalla", "screenshot"), ("minimiza todo", "minimize"),
           ("silencia|mutea", "mute")],
    "it": [("apri|aprire|avvia|lancia", "open"), ("chiudi|chiudere|esci da", "close"), ("riproduci|suona|metti", "play"),
           ("pausa|metti in pausa", "pause"), ("riprendi|continua", "resume"),
           ("prossima canzone|prossima|successiva", "next"), ("canzone precedente|precedente", "previous"),
           ("più forte|alza il volume", "louder"), ("più piano|abbassa il volume", "quieter"),
           ("che ore sono|che ora è", "time"), ("che tempo fa|meteo", "weather"),
           ("fai uno screenshot|cattura schermo|screenshot", "screenshot"), ("riduci tutto", "minimize"),
           ("silenzia|muto", "mute")],
    "pt": [("abre|abrir|abra|inicia|iniciar", "open"), ("fecha|fechar|feche|sai do", "close"),
           ("toca|tocar|reproduz|reproduzir|coloca|põe", "play"), ("pausa|pausar", "pause"),
           ("continua|continuar|retoma", "resume"), ("próxima música|próxima|seguinte", "next"),
           ("música anterior|anterior", "previous"), ("mais alto|aumenta o volume", "louder"),
           ("mais baixo|abaixa o volume|diminui o volume", "quieter"), ("que horas são", "time"),
           ("como está o tempo|previsão do tempo|tempo", "weather"),
           ("tira um print|captura de tela|captura de ecrã", "screenshot"), ("minimiza tudo", "minimize"),
           ("silencia|muta", "mute")],
    "nl": [("open|openen|start|starten", "open"), ("sluit|sluiten|afsluiten", "close"), ("speel|afspelen", "play"),
           ("pauze|pauzeer|pauzeren", "pause"), ("ga verder|hervat", "resume"),
           ("volgend nummer|volgende", "next"), ("vorig nummer|vorige", "previous"), ("harder|luider", "louder"),
           ("zachter", "quieter"), ("hoe laat is het", "time"), ("hoe is het weer|weer", "weather"),
           ("maak een screenshot|schermafbeelding", "screenshot"), ("alles minimaliseren", "minimize"),
           ("dempen", "mute")],
    "pl": [("otwórz|otworz|uruchom|włącz", "open"), ("zamknij|wyłącz", "close"), ("odtwórz|puść|zagraj", "play"),
           ("pauza|zatrzymaj", "pause"), ("wznów|kontynuuj", "resume"), ("następna piosenka|następny|dalej", "next"),
           ("poprzednia piosenka|poprzedni", "previous"), ("głośniej", "louder"), ("ciszej", "quieter"),
           ("która godzina|ktora godzina", "time"), ("jaka jest pogoda|pogoda", "weather"),
           ("zrób zrzut ekranu|zrzut ekranu", "screenshot"), ("zminimalizuj wszystko", "minimize"),
           ("wycisz", "mute")],
    "ru": [("открой|открыть|запусти|включи", "open"), ("закрой|закрыть|выключи", "close"),
           ("воспроизведи|поставь|сыграй", "play"), ("пауза|останови музыку", "pause"),
           ("продолжи|продолжить", "resume"), ("следующая песня|следующий|следующая", "next"),
           ("предыдущая песня|предыдущий|предыдущая", "previous"), ("громче", "louder"), ("тише", "quieter"),
           ("который час|сколько времени", "time"), ("какая погода|погода", "weather"),
           ("сделай скриншот|скриншот", "screenshot"), ("сверни всё|сверни все", "minimize"),
           ("выключи микрофон", "mute")],
    "uk": [("відкрий|відкрити|запусти|увімкни", "open"), ("закрий|закрити|вимкни", "close"),
           ("відтвори|постав|зіграй", "play"), ("пауза|зупини музику", "pause"), ("продовж|продовжити", "resume"),
           ("наступна пісня|наступний|наступна", "next"), ("попередня пісня|попередній|попередня", "previous"),
           ("голосніше", "louder"), ("тихіше", "quieter"), ("котра година|скільки часу", "time"),
           ("яка погода|погода", "weather"), ("зроби скріншот|скріншот", "screenshot"),
           ("згорни все", "minimize"), ("вимкни мікрофон", "mute")],
    "sv": [("öppna|starta", "open"), ("stäng|avsluta", "close"), ("spela", "play"), ("pausa", "pause"),
           ("fortsätt", "resume"), ("nästa låt|nästa", "next"), ("föregående låt|föregående", "previous"),
           ("högre", "louder"), ("tystare|lägre", "quieter"), ("vad är klockan", "time"),
           ("hur är vädret|vädret", "weather"), ("ta en skärmdump|skärmdump", "screenshot"),
           ("minimera allt", "minimize"), ("stäng av ljudet", "mute")],
    "da": [("åbn|åben|start", "open"), ("luk|afslut", "close"), ("afspil|spil", "play"), ("pause", "pause"),
           ("fortsæt", "resume"), ("næste sang|næste", "next"), ("forrige sang|forrige", "previous"),
           ("højere", "louder"), ("lavere|stille", "quieter"), ("hvad er klokken", "time"),
           ("hvordan er vejret|vejret", "weather"), ("tag et skærmbillede|skærmbillede", "screenshot"),
           ("minimer alt", "minimize"), ("slå lyden fra", "mute")],
    "fi": [("avaa|käynnistä", "open"), ("sulje|lopeta", "close"), ("soita|toista", "play"),
           ("tauko|pysäytä", "pause"), ("jatka", "resume"), ("seuraava kappale|seuraava", "next"),
           ("edellinen kappale|edellinen", "previous"), ("kovemmalle|lujempaa", "louder"),
           ("hiljemmalle|hiljempaa", "quieter"), ("paljonko kello on|mitä kello on", "time"),
           ("millainen sää|sää", "weather"), ("ota kuvakaappaus|kuvakaappaus", "screenshot"),
           ("pienennä kaikki", "minimize"), ("mykistä", "mute")],
    "cs": [("otevři|otevřít|spusť", "open"), ("zavři|zavřít|ukonči", "close"), ("přehraj|pusť|hraj", "play"),
           ("pauza|pozastav", "pause"), ("pokračuj", "resume"), ("další písnička|další", "next"),
           ("předchozí písnička|předchozí", "previous"), ("hlasitěji", "louder"), ("tišeji|potichu", "quieter"),
           ("kolik je hodin", "time"), ("jaké je počasí|počasí", "weather"),
           ("udělej snímek obrazovky|snímek obrazovky", "screenshot"), ("minimalizuj vše", "minimize"),
           ("ztlum mikrofon", "mute")],
    "sk": [("otvor|otvoriť|spusti", "open"), ("zavri|zavrieť|ukonči", "close"), ("prehraj|pusti|hraj", "play"),
           ("pauza|pozastav", "pause"), ("pokračuj", "resume"), ("ďalšia pieseň|ďalšia|ďalší", "next"),
           ("predchádzajúca pieseň|predchádzajúca", "previous"), ("hlasnejšie", "louder"), ("tichšie", "quieter"),
           ("koľko je hodín", "time"), ("aké je počasie|počasie", "weather"),
           ("urob snímku obrazovky|snímka obrazovky", "screenshot"), ("minimalizuj všetko", "minimize"),
           ("stlm mikrofón", "mute")],
    "sl": [("odpri|zaženi", "open"), ("zapri|končaj", "close"), ("predvajaj|zaigraj", "play"),
           ("premor|ustavi", "pause"), ("nadaljuj", "resume"), ("naslednja pesem|naslednja", "next"),
           ("prejšnja pesem|prejšnja", "previous"), ("glasneje", "louder"), ("tišje", "quieter"),
           ("koliko je ura", "time"), ("kakšno je vreme|vreme", "weather"),
           ("naredi posnetek zaslona|posnetek zaslona", "screenshot"), ("pomanjšaj vse", "minimize"),
           ("utišaj mikrofon", "mute")],
    "hr": [("otvori|pokreni", "open"), ("zatvori|ugasi", "close"), ("pusti|sviraj|reproduciraj", "play"),
           ("pauza|zaustavi", "pause"), ("nastavi", "resume"), ("sljedeća pjesma|sljedeća|sljedeći", "next"),
           ("prethodna pjesma|prethodna", "previous"), ("glasnije", "louder"), ("tiše", "quieter"),
           ("koliko je sati", "time"), ("kakvo je vrijeme|vrijeme", "weather"),
           ("napravi snimku zaslona|snimka zaslona", "screenshot"), ("smanji sve", "minimize"),
           ("utišaj mikrofon", "mute")],
    "bg": [("отвори|пусни програмата|стартирай", "open"), ("затвори|спри програмата", "close"),
           ("пусни|изсвири", "play"), ("пауза", "pause"), ("продължи", "resume"),
           ("следваща песен|следваща", "next"), ("предишна песен|предишна", "previous"),
           ("по-силно|по силно", "louder"), ("по-тихо|по тихо", "quieter"), ("колко е часът", "time"),
           ("какво е времето|времето", "weather"), ("направи скрийншот|скрийншот", "screenshot"),
           ("минимизирай всичко", "minimize"), ("заглуши микрофона", "mute")],
    "ro": [("deschide|pornește", "open"), ("închide|oprește aplicația", "close"), ("redă|pune|cântă", "play"),
           ("pauză", "pause"), ("continuă", "resume"), ("melodia următoare|următoarea", "next"),
           ("melodia anterioară|anterioara", "previous"), ("mai tare", "louder"), ("mai încet", "quieter"),
           ("cât e ceasul|ce oră este", "time"), ("cum e vremea|vremea", "weather"),
           ("fă o captură de ecran|captură de ecran", "screenshot"), ("minimizează tot", "minimize"),
           ("oprește microfonul", "mute")],
    "hu": [("nyisd meg|nyisd|indítsd el|indítsd", "open"), ("zárd be|zárd|lépj ki", "close"),
           ("játszd le|játszd|indítsd a zenét", "play"), ("szünet|állítsd meg", "pause"), ("folytasd", "resume"),
           ("következő dal|következő", "next"), ("előző dal|előző", "previous"), ("hangosabban|hangosabb", "louder"),
           ("halkabban|halkabb", "quieter"), ("hány óra van", "time"), ("milyen az idő|időjárás", "weather"),
           ("készíts képernyőképet|képernyőkép", "screenshot"), ("minimalizálj mindent", "minimize"),
           ("némítsd a mikrofont", "mute")],
    "el": [("άνοιξε|ανοιξε", "open"), ("κλείσε|κλεισε", "close"), ("παίξε|βάλε", "play"), ("παύση", "pause"),
           ("συνέχισε", "resume"), ("επόμενο τραγούδι|επόμενο", "next"), ("προηγούμενο τραγούδι|προηγούμενο", "previous"),
           ("πιο δυνατά", "louder"), ("πιο σιγά", "quieter"), ("τι ώρα είναι", "time"),
           ("τι καιρό κάνει|καιρός", "weather"), ("τράβηξε στιγμιότυπο οθόνης|στιγμιότυπο οθόνης", "screenshot"),
           ("ελαχιστοποίησε όλα", "minimize"), ("σίγαση μικροφώνου", "mute")],
    "et": [("ava|käivita", "open"), ("sulge", "close"), ("mängi|esita", "play"), ("paus|peata", "pause"),
           ("jätka", "resume"), ("järgmine laul|järgmine", "next"), ("eelmine laul|eelmine", "previous"),
           ("valjemini|valjemaks", "louder"), ("vaiksemalt|vaiksemaks", "quieter"), ("mis kell on", "time"),
           ("milline on ilm|ilm", "weather"), ("tee ekraanipilt|ekraanipilt", "screenshot"),
           ("minimeeri kõik", "minimize"), ("vaigista mikrofon", "mute")],
    "lv": [("atver|palaid", "open"), ("aizver|aizvērt", "close"), ("atskaņo|spēlē", "play"), ("pauze|apturi", "pause"),
           ("turpini", "resume"), ("nākamā dziesma|nākamā", "next"), ("iepriekšējā dziesma|iepriekšējā", "previous"),
           ("skaļāk", "louder"), ("klusāk", "quieter"), ("cik ir pulkstenis", "time"),
           ("kāds ir laiks|laikapstākļi", "weather"), ("uzņem ekrānuzņēmumu|ekrānuzņēmums", "screenshot"),
           ("minimizē visu", "minimize"), ("izslēdz mikrofonu", "mute")],
    "lt": [("atidaryk|paleisk", "open"), ("uždaryk|išjunk", "close"), ("grok|paleisk dainą", "play"),
           ("pauzė|sustabdyk", "pause"), ("tęsk", "resume"), ("kita daina|kita", "next"),
           ("ankstesnė daina|ankstesnė", "previous"), ("garsiau", "louder"), ("tyliau", "quieter"),
           ("kiek valandų", "time"), ("koks oras|oras", "weather"),
           ("padaryk ekrano nuotrauką|ekrano nuotrauka", "screenshot"), ("sumažink viską", "minimize"),
           ("išjunk mikrofoną", "mute")],
    "mt": [("iftaħ", "open"), ("agħlaq", "close"), ("daqq|ħaddem", "play"), ("waqfa|pawża", "pause"),
           ("kompli", "resume"), ("il-kanzunetta li jmiss|li jmiss", "next"), ("ta' qabel", "previous"),
           ("aktar qawwi", "louder"), ("aktar baxx", "quieter"), ("x'ħin hu", "time"), ("kif inhu t-temp|it-temp", "weather"),
           ("ħu screenshot|screenshot", "screenshot"), ("naqqas kollox", "minimize"), ("itfi l-mikrofonu", "mute")],
}
ARTICLES = r"(?:the|le|la|les|l|el|los|las|il|lo|gli|o|a|os|as|de|het|een|der|die|das|den|dem|ein|eine|en|ett|το|τη|την|τον|η|ο|az)"


def to_english(text: str, code: str | None = None) -> str:
    """The everyday command at the start of what you said, in English words - the rest as you said it.
    "Öffne Discord" -> "open discord"; "wie spät ist es" -> "what time is it". Not a known command: as it was."""
    code = code or _current
    t = re.sub(r"\s+", " ", (text or "").strip().lower().strip(".!?¿¡"))
    phrases = sorted(((w, meaning) for words, meaning in COMMANDS.get(code, ()) for w in words.split("|")),
                     key=lambda pair: -len(pair[0]))                  # "mets en pause" before "mets"
    for w, meaning in phrases:
        if t == w or t.startswith(w + " "):
            rest = re.sub(rf"^{ARTICLES}\s+", "", t[len(w):].strip())
            english_words = _C[meaning]
            if meaning in ("open", "close", "play"):
                return f"{english_words} {latin(rest)}".strip() if rest else t
            return english_words
    # Misheard a little ("wie schwer ist es" for "wie spät ist es"): a whole-sentence command that's nearly it.
    # (Only the ones that take nothing after them - never a guess at an app name.)
    from difflib import SequenceMatcher
    best, score = "", 0.0
    for w, meaning in phrases:
        if meaning in ("open", "close", "play") or len(w) < 6:
            continue
        r = SequenceMatcher(None, t, w).ratio()
        if r > score:
            best, score = meaning, r
    if score >= NEAR:
        return _C[best]
    return text


NEAR = 0.78             # how close a misheard whole-sentence command must be


_TRANSLIT = dict(zip("абвгдежзийклмнопрстуфхцчшщъыьэюяєіїґ",
                     ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                      "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya", "ye", "i", "yi", "g"]))
_TRANSLIT.update(dict(zip("αβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώ",
                          ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o", "p", "r", "s",
                           "s", "t", "y", "f", "ch", "ps", "o", "a", "e", "i", "i", "o", "y", "o"])))
_TRANSLIT["ё"] = "yo"


def latin(text: str) -> str:
    """Cyrillic / Greek letters in Latin ones, for app names ("дискорд" -> "diskord", "стим" -> "stim"): her app
    matching is in Latin letters and finds the closest app from there."""
    return "".join(_TRANSLIT.get(ch, ch) for ch in text)


def reply_rule(code: str | None = None) -> str:
    """The line added to the AI's instructions so it answers in your language ("" in English)."""
    lang = get(code)
    if lang.code == "en":
        return ""
    return (f"The user speaks {lang.name}. Always reply in {lang.name} ({lang.native}), whatever language "
            f"this prompt is in. Tool arguments (app names, songs, search words) stay as the user said them.")
