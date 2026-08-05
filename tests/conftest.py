"""Keep tests deterministic regardless of a developer's local .env file."""

import os


_TEST_ENV = {
    "CONTRACT_TTS_ENGINE": "gptsovits",
    "CONTRACT_TTS_ENGINE_YUE": "",
    "CONTRACT_TTS_ENGINE_ZH": "",
    "CONTRACT_TTS_ENGINE_EN": "",
    "DASHSCOPE_API_KEY": "",
    "GPTSOVITS_ENGINE_URL": "http://127.0.0.1:9880",
    "GPTSOVITS_REF_AUDIO": "refs/cantonese_ref_trim.wav",
    "GPTSOVITS_REF_PROMPT": "refs/cantonese_ref_trim.txt",
    "GPTSOVITS_REF_PROMPT_LANG": "yue",
    "GPTSOVITS_REF_AUDIO_YUE": "",
    "GPTSOVITS_REF_AUDIO_ENGINE_PATH_YUE": "",
    "GPTSOVITS_REF_PROMPT_YUE": "",
    "GPTSOVITS_REF_PROMPT_LANG_YUE": "",
    "GPTSOVITS_REF_AUDIO_ZH": "",
    "GPTSOVITS_REF_AUDIO_ENGINE_PATH_ZH": "",
    "GPTSOVITS_REF_PROMPT_ZH": "",
    "GPTSOVITS_REF_PROMPT_LANG_ZH": "",
    "GPTSOVITS_REF_AUDIO_EN": "",
    "GPTSOVITS_REF_AUDIO_ENGINE_PATH_EN": "",
    "GPTSOVITS_REF_PROMPT_EN": "",
    "GPTSOVITS_REF_PROMPT_LANG_EN": "",
    "BAILIAN_TRANSPORT": "http",
    "BAILIAN_HTTP_BASE_URL": "https://dashscope.aliyuncs.com",
    "BAILIAN_WS_URL": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
    "BAILIAN_MODEL": "cosyvoice-v3-flash",
    "BAILIAN_WORKSPACE_ID": "",
    "BAILIAN_VOICE": "longjiaxin_v3",
    "BAILIAN_VOICE_ZH": "longxiaochun",
    "BAILIAN_VOICE_EN": "longanyang",
    "ENGINE_PROFILE_CACHE_VERSION_YUE": "v1",
    "ENGINE_PROFILE_CACHE_VERSION_ZH": "v1",
    "ENGINE_PROFILE_CACHE_VERSION_EN": "v1",
}

os.environ.update(_TEST_ENV)
