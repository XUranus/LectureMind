interface SupportModelConfigItem {
    name : string,
    value : string,
    local : boolean // if is a local hugging-face model or a openai API model
}

export const SUPPORT_MODELS : SupportModelConfigItem[] = [
    // Local Hugging Face Models
    {
        name : "Qwen/Qwen2.5-0.5B-Instruct",
        value : "Qwen/Qwen2.5-0.5B-Instruct",
        local : true,
    },
    // Remote Aliyun Models via OpenAI API
    {
        name : "Aliyun/Qwen2.5-0.5B-Instruct",
        value : "qwen2.5-0.5b-instruct",
        local : false,
    }, {
        name : "Aliyun/Qwen2.5-1.5B-Instruct",
        value : "qwen2.5-1.5b-instruct",
        local : false,
    }, {
        name : "Aliyun/Qwen2.5-3B-Instruct",
        value : "qwen2.5-3b-instruct",
        local : false,
    }, {
        name : "Aliyun/Qwen2.5-7B-Instruct",
        value : "qwen2.5-7b-instruct",
        local : false,
    }, {
        name : "Aliyun/qwen-turbo",
        value : "qwen-turbo",
        local : false,
    }
]

export const DEFAULT_MODEL : string = "qwen2.5-0.5b-instruct"

// API_PREFIX is injected at container start via /env-config.js → window.__ENV__.
// Falls back to the development default so `pnpm start` keeps working without Docker.
declare global {
    interface Window {
        __ENV__?: { API_PREFIX?: string }
    }
}
export const API_PREFIX : string =
    window.__ENV__?.API_PREFIX ?? "http://127.0.0.1:8000"

export default {
    SUPPORT_MODELS,
    DEFAULT_MODEL,
    API_PREFIX,
}