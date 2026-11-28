"use strict";
/* Frontend UI message catalogs and English-fallback translator across six languages. */
(function (root) {
  const LOCALES = {en: undefined, hi: "hi-IN", te: "te-IN", ta: "ta-IN", bn: "bn-IN", mr: "mr-IN"};
  const PACKS = {
    en: {
      cat_routine: "\uD83D\uDD52 Daily routine", cat_indoor: "\uD83C\uDFE0 Indoor air", cat_alternative: "\uD83C\uDF31 Sustainable alternative",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "Estimated exposure reduction {pct} percent",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "Estimated exposure reduction {pct}%",
      top_three: "Top 3 today", exposure_note: "Follow this plan: about {pct}% less pollution exposure (rough estimate)",
      myth_prefix: "Myth buster: ", source_gemini: "\u2728 Briefing written by Gemini", source_rules: "Briefing from built-in rules",
      your_actions: "Your actions", impact_prefix: "Impact: ", building_plan: "Building your plan\u2026",
      reading_source: "Source: {source}", reading_time: ". Reading time: {time} ({rel})",
      reading_min_ago: "{n} min ago", reading_h_ago: "{n} h ago", reading_stale: ". This reading may be out of date.",
      enter_city: "Enter a city above first.", no_places: "No places found within 4 km. Try searching a nearby larger city.",
      stale_places: "Showing results from earlier today because the public map servers are busy.",
      osm_attr: "Data \u00a9 OpenStreetMap contributors. Opening hours, mask stock and indoor air quality are not verified: call ahead.",
      need_coords: "Use my location, or pick a city from the suggestions, then build your plan first.",
      searching_nearby: "Searching nearby places\u2026 this can take up to 30 seconds.",
      osm_open: "Open this area on OpenStreetMap", try_again: "Try again",
      nearby_hospital: "Hospital or clinic", nearby_pharmacy: "Pharmacy", nearby_library: "Library", nearby_mall: "Mall",
      unit_m: "m", unit_km: "km",
      image_reading: "AI is reading the image\u2026", image_found: "AQI {aqi} found. {note}",
      image_no_num: "No AQI number found. Visibility: {vis}. Please type the AQI.",
      image_bad_type: "Use a PNG, JPEG or WebP image.", image_too_big: "Image must be under 3 MB.",
    },
    hi: {
      cat_routine: "\uD83D\uDD52 दैनिक दिनचर्या", cat_indoor: "\uD83C\uDFE0 घर के अंदर की हवा", cat_alternative: "\uD83C\uDF31 टिकाऊ विकल्प",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "अनुमानित संपर्क में कमी {pct} प्रतिशत",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "अनुमानित संपर्क में कमी {pct}%",
      top_three: "आज के मुख्य 3 कदम", exposure_note: "इस योजना को अपनाएं: प्रदूषण संपर्क में लगभग {pct}% कमी (मोटा अनुमान)",
      myth_prefix: "भ्रम निवारण: ", source_gemini: "\u2728 Gemini द्वारा तैयार सारांश", source_rules: "नियमों पर आधारित सारांश",
      your_actions: "आपके कदम", impact_prefix: "प्रभाव: ", building_plan: "आपकी योजना बन रही है\u2026",
      reading_source: "स्रोत: {source}", reading_time: ". मापन समय: {time} ({rel})",
      reading_min_ago: "{n} मिनट पहले", reading_h_ago: "{n} घंटे पहले", reading_stale: ". यह रीडिंग पुरानी हो सकती है।",
      enter_city: "पहले ऊपर कोई शहर दर्ज करें।", no_places: "4 किमी के भीतर कोई स्थान नहीं मिला। पास का बड़ा शहर खोजें।",
      stale_places: "सार्वजनिक मानचित्र सर्वर व्यस्त होने से आज पहले के परिणाम दिखाए जा रहे हैं।",
      osm_attr: "डेटा \u00a9 OpenStreetMap योगदानकर्ता। खुलने का समय, मास्क स्टॉक और अंदर की हवा सत्यापित नहीं हैं: पहले कॉल करें।",
      need_coords: "मेरा स्थान उपयोग करें या सुझावों से शहर चुनें, फिर पहले योजना बनाएं।",
      searching_nearby: "पास के स्थान खोजे जा रहे हैं\u2026 इसमें 30 सेकंड तक लग सकते हैं।",
      osm_open: "इस क्षेत्र को OpenStreetMap पर खोलें", try_again: "फिर से प्रयास करें",
      nearby_hospital: "अस्पताल या क्लिनिक", nearby_pharmacy: "दवा की दुकान", nearby_library: "पुस्तकालय", nearby_mall: "शॉपिंग मॉल",
      unit_m: "मी", unit_km: "किमी",
      image_reading: "AI छवि पढ़ रहा है\u2026", image_found: "AQI {aqi} मिला। {note}",
      image_no_num: "कोई AQI संख्या नहीं मिली। दृश्यता: {vis}। कृपया AQI लिखें।",
      image_bad_type: "PNG, JPEG या WebP छवि का उपयोग करें।", image_too_big: "छवि 3 MB से कम होनी चाहिए।",
    },
    te: {
      cat_routine: "\uD83D\uDD52 రోజువారీ దినచర్య", cat_indoor: "\uD83C\uDFE0 ఇంటి లోపలి గాలి", cat_alternative: "\uD83C\uDF31 స్థిరమైన ప్రత్యామ్నాయం",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "అంచనా కాలుష్య తగ్గింపు {pct} శాతం",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "అంచనా కాలుష్య తగ్గింపు {pct}%",
      top_three: "ఈరోజు ముఖ్యమైన 3 సూచనలు", exposure_note: "ఈ ప్రణాళిక పాటించండి: కాలుష్య ప్రభావం సుమారు {pct}% తగ్గుతుంది (అంచనా)",
      myth_prefix: "అపోహ తొలగింపు: ", source_gemini: "\u2728 Gemini రాసిన సారాంశం", source_rules: "నియమాల ఆధారిత సారాంశం",
      your_actions: "మీ చర్యలు", impact_prefix: "ప్రభావం: ", building_plan: "మీ ప్రణాళిక రూపొందుతోంది\u2026",
      reading_source: "మూలం: {source}", reading_time: ". రీడింగ్ సమయం: {time} ({rel})",
      reading_min_ago: "{n} నిమిషాల క్రితం", reading_h_ago: "{n} గంటల క్రితం", reading_stale: ". ఈ రీడింగ్ పాతదై ఉండవచ్చు.",
      enter_city: "ముందుగా పైన నగరాన్ని నమోదు చేయండి.", no_places: "4 కి.మీ. లోపల ప్రదేశాలు దొరకలేదు. దగ్గరలోని పెద్ద నగరాన్ని శోధించండి.",
      stale_places: "పబ్లిక్ మ్యాప్ సర్వర్లు బిజీగా ఉన్నందున ఈరోజు ముందుగా సేకరించిన ఫలితాలు చూపుతున్నాము.",
      osm_attr: "డేటా \u00a9 OpenStreetMap సహాయకులు. తెరిచే వేళలు, మాస్క్ నిల్వ మరియు లోపలి గాలి నాణ్యత ధృవీకరించబడలేదు: ముందుగా ఫోన్ చేయండి.",
      need_coords: "నా స్థానాన్ని వాడండి లేదా సూచనల నుండి నగరాన్ని ఎంచుకుని ముందుగా ప్రణాళికను రూపొందించండి.",
      searching_nearby: "సమీప ప్రదేశాలను వెతుకుతోంది\u2026 దీనికి 30 సెకన్ల వరకు పట్టవచ్చు.",
      osm_open: "ఈ ప్రాంతాన్ని OpenStreetMapలో తెరవండి", try_again: "మళ్ళీ ప్రయత్నించండి",
      nearby_hospital: "ఆసుపత్రి లేదా క్లినిక్", nearby_pharmacy: "మందుల దుకాణం", nearby_library: "గ్రంథాలయం", nearby_mall: "మాల్",
      unit_m: "మీ.", unit_km: "కి.మీ.",
      image_reading: "AI చిత్రాన్ని చదువుతోంది\u2026", image_found: "AQI {aqi} కనుగొనబడింది. {note}",
      image_no_num: "AQI సంఖ్య కనిపించలేదు. దృశ్యమానత: {vis}. దయచేసి AQI టైప్ చేయండి.",
      image_bad_type: "PNG, JPEG లేదా WebP చిత్రాన్ని వాడండి.", image_too_big: "చిత్రం 3 MB కంటే తక్కువగా ఉండాలి.",
    },
    ta: {
      cat_routine: "\uD83D\uDD52 தினசரி வழக்கம்", cat_indoor: "\uD83C\uDFE0 உள்ளறை காற்று", cat_alternative: "\uD83C\uDF31 நிலையான மாற்று",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "மதிப்பிடப்பட்ட பாதிப்பு குறைப்பு {pct} சதவீதம்",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "மதிப்பிடப்பட்ட பாதிப்பு குறைப்பு {pct}%",
      top_three: "இன்றைய முக்கிய 3 படிகள்", exposure_note: "இந்த திட்டத்தை பின்பற்றவும்: மாசு பாதிப்பு சுமார் {pct}% குறையும் (தோராய மதிப்பீடு)",
      myth_prefix: "தவறான நம்பிக்கை நீக்கம்: ", source_gemini: "\u2728 Gemini எழுதிய சுருக்கம்", source_rules: "விதி அடிப்படையிலான சுருக்கம்",
      your_actions: "உங்கள் நடவடிக்கைகள்", impact_prefix: "தாக்கம்: ", building_plan: "உங்கள் திட்டம் உருவாகிறது\u2026",
      reading_source: "ஆதாரம்: {source}", reading_time: ". அளவீட்டு நேரம்: {time} ({rel})",
      reading_min_ago: "{n} நிமி முன்பு", reading_h_ago: "{n} மணி முன்பு", reading_stale: ". இந்த அளவீடு பழையதாக இருக்கலாம்.",
      enter_city: "முதலில் மேலே ஒரு நகரத்தை உள்ளிடவும்.", no_places: "4 கி.மீ.க்குள் இடங்கள் கிடைக்கவில்லை. அருகிலுள்ள பெரிய நகரத்தை தேடுங்கள்.",
      stale_places: "பொது வரைபட சேவையகங்கள் பிஸியாக உள்ளதால் இன்று முந்தைய முடிவுகள் காட்டப்படுகின்றன.",
      osm_attr: "தரவு \u00a9 OpenStreetMap பங்களிப்பாளர்கள். திறக்கும் நேரம், முகக்கவச இருப்பு மற்றும் உள்ளறை காற்று தரம் சரிபார்க்கப்படவில்லை: முன் அழைக்கவும்.",
      need_coords: "என் இடத்தைப் பயன்படுத்துங்கள் அல்லது பரிந்துரைகளில் நகரத்தை தேர்ந்து முதலில் திட்டம் உருவாக்குங்கள்.",
      searching_nearby: "அருகிலுள்ள இடங்களை தேடுகிறது\u2026 இதற்கு 30 வினாடிகள் வரை ஆகலாம்.",
      osm_open: "இந்தப் பகுதியை OpenStreetMap-இல் திறக்கவும்", try_again: "மீண்டும் முயற்சி செய்க",
      nearby_hospital: "மருத்துவமனை அல்லது கிளினிக்", nearby_pharmacy: "மருந்தகம்", nearby_library: "நூலகம்", nearby_mall: "வணிக வளாகம்",
      unit_m: "மீ", unit_km: "கி.மீ.",
      image_reading: "AI படத்தை படிக்கிறது\u2026", image_found: "AQI {aqi} கிடைத்தது. {note}",
      image_no_num: "AQI எண் கிடைக்கவில்லை. தெளிவுத்தன்மை: {vis}. AQI-ஐ தட்டச்சு செய்யவும்.",
      image_bad_type: "PNG, JPEG அல்லது WebP படத்தைப் பயன்படுத்தவும்.", image_too_big: "படம் 3 MB-க்கு குறைவாக இருக்க வேண்டும்.",
    },
    bn: {
      cat_routine: "\uD83D\uDD52 দৈনন্দিন রুটিন", cat_indoor: "\uD83C\uDFE0 ঘরের ভেতরের বাতাস", cat_alternative: "\uD83C\uDF31 টেকসই বিকল্প",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "আনুমানিক ঝুঁকি হ্রাস {pct} শতাংশ",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "আনুমানিক ঝুঁকি হ্রাস {pct}%",
      top_three: "আজকের শীর্ষ ৩টি কাজ", exposure_note: "এই পরিকল্পনা মানুন: দূষণের ঝুঁকি প্রায় {pct}% কম (আনুমানিক হিসাব)",
      myth_prefix: "ভুল ধারণা ভাঙন: ", source_gemini: "\u2728 Gemini-র লেখা সারসংক্ষেপ", source_rules: "নিয়মভিত্তিক সারসংক্ষেপ",
      your_actions: "আপনার করণীয়", impact_prefix: "প্রভাব: ", building_plan: "আপনার পরিকল্পনা তৈরি হচ্ছে\u2026",
      reading_source: "উৎস: {source}", reading_time: ". পরিমাপের সময়: {time} ({rel})",
      reading_min_ago: "{n} মিনিট আগে", reading_h_ago: "{n} ঘণ্টা আগে", reading_stale: ". এই তথ্যটি পুরোনো হতে পারে।",
      enter_city: "প্রথমে উপরে একটি শহর লিখুন।", no_places: "৪ কিমির মধ্যে কোনো স্থান পাওয়া যায়নি। কাছের বড় শহরে খুঁজুন।",
      stale_places: "পাবলিক ম্যাপ সার্ভার ব্যস্ত থাকায় আজকের আগের ফলাফল দেখানো হচ্ছে।",
      osm_attr: "তথ্য \u00a9 OpenStreetMap অবদানকারী। খোলার সময়, মাস্কের মজুত ও ভেতরের বায়ুমান যাচাই করা নয়: আগে ফোন করুন।",
      need_coords: "আমার অবস্থান ব্যবহার করুন বা তালিকা থেকে শহর বেছে প্রথমে পরিকল্পনা তৈরি করুন।",
      searching_nearby: "কাছের স্থান খোঁজা হচ্ছে\u2026 এতে ৩০ সেকেন্ড পর্যন্ত সময় লাগতে পারে।",
      osm_open: "মানচিত্রে এই এলাকা খুলুন", try_again: "আবার চেষ্টা করুন",
      nearby_hospital: "হাসপাতাল বা ক্লিনিক", nearby_pharmacy: "ওষুধের দোকান", nearby_library: "গ্রন্থাগার", nearby_mall: "শপিং মল",
      unit_m: "মি", unit_km: "কিমি",
      image_reading: "AI ছবি পড়ছে\u2026", image_found: "AQI {aqi} পাওয়া গেছে। {note}",
      image_no_num: "AQI সংখ্যা পাওয়া যায়নি। দৃশ্যমানতা: {vis}। অনুগ্রহ করে AQI লিখুন।",
      image_bad_type: "PNG, JPEG বা WebP ছবি ব্যবহার করুন।", image_too_big: "ছবি ৩ MB-এর কম হতে হবে।",
    },
    mr: {
      cat_routine: "\uD83D\uDD52 दैनंदिन वेळापत्रक", cat_indoor: "\uD83C\uDFE0 घरातील हवा", cat_alternative: "\uD83C\uDF31 शाश्वत पर्याय",
      us_aqi: "US AQI", gauge_aria: "AQI {aqi}", meter_aria: "अंदाजे संपर्क घट {pct} टक्के",
      sr_aqi: "US AQI {aqi} ({band})", sr_meter: "अंदाजे संपर्क घट {pct}%",
      top_three: "आजचे प्रमुख ३ उपाय", exposure_note: "ही योजना पाळा: प्रदूषण संपर्क सुमारे {pct}% कमी (अंदाज)",
      myth_prefix: "गैरसमज दूर करा: ", source_gemini: "\u2728 Gemini ने लिहिलेला सारांश", source_rules: "नियमांवर आधारित सारांश",
      your_actions: "तुमचे उपाय", impact_prefix: "परिणाम: ", building_plan: "तुमची योजना तयार होत आहे\u2026",
      reading_source: "स्रोत: {source}", reading_time: ". मोजमाप वेळ: {time} ({rel})",
      reading_min_ago: "{n} मिनिटांपूर्वी", reading_h_ago: "{n} तासांपूर्वी", reading_stale: ". ही नोंद जुनी असू शकते.",
      enter_city: "प्रथम वर शहर नोंदवा.", no_places: "४ किमीमध्ये ठिकाणे सापडली नाहीत. जवळचे मोठे शहर शोधा.",
      stale_places: "सार्वजनिक नकाशा सर्व्हर व्यस्त असल्याने आजचे आधीचे निकाल दाखवले आहेत.",
      osm_attr: "डेटा \u00a9 OpenStreetMap योगदानकर्ते. वेळ, मास्क साठा व घरातील हवा तपासलेली नाही: आधी फोन करा.",
      need_coords: "माझे स्थान वापरा किंवा सुचवलेल्या शहरांमधून निवडून आधी योजना तयार करा.",
      searching_nearby: "जवळपासची ठिकाणे शोधत आहे\u2026 यास ३० सेकंदांपर्यंत लागू शकतात.",
      osm_open: "हा परिसर OpenStreetMap वर उघडा", try_again: "पुन्हा प्रयत्न करा",
      nearby_hospital: "रुग्णालय किंवा क्लिनिक", nearby_pharmacy: "औषधांचे दुकान", nearby_library: "ग्रंथालय", nearby_mall: "मॉल",
      unit_m: "मी", unit_km: "किमी",
      image_reading: "AI प्रतिमा वाचत आहे\u2026", image_found: "AQI {aqi} आढळला. {note}",
      image_no_num: "AQI संख्या आढळली नाही. दृश्यमानता: {vis}. कृपया AQI टाइप करा.",
      image_bad_type: "PNG, JPEG किंवा WebP प्रतिमा वापरा.", image_too_big: "प्रतिमा ३ MB पेक्षा लहान असावी.",
    },
  };

  /**
   * Normalize an ISO language tag against the six supported languages.
   * @param {string|null|undefined} lang Candidate language code.
   * @returns {"en"|"hi"|"te"|"ta"|"bn"|"mr"} Supported language code defaulting to "en".
   */
  function normalizeLang(lang) {
    return Object.hasOwn(PACKS, lang) ? lang : "en";
  }

  /**
   * Return the BCP 47 locale tag associated with a supported language.
   * @param {string|null|undefined} lang Language code.
   * @returns {string|undefined} Locale tag or undefined for runtime default.
   */
  function localeFor(lang) {
    return LOCALES[normalizeLang(lang)];
  }

  /**
   * Format a localized frontend message with safe English fallback and parameter substitution.
   * @param {string|null|undefined} lang Language code.
   * @param {string} key Message identifier key.
   * @param {Record<string, string|number>} [params] Optional placeholder values.
   * @returns {string} Localized formatted text (or empty string if unknown key).
   */
  function tr(lang, key, params) {
    const code = normalizeLang(lang);
    const tmpl = PACKS[code][key] || PACKS.en[key] || "";
    if (!tmpl || !params) return tmpl;
    return tmpl.replace(/\{([a-zA-Z0-9_]+)\}/g, (m, k) => (Object.hasOwn(params, k) ? String(params[k]) : m));
  }

  const api = {PACKS, normalizeLang, localeFor, tr};
  root.CleanAirI18n = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
