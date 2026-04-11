import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Button, message, Spin, Divider, Typography, Tag } from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { API_PREFIX } from '../config';

const { Title, Text } = Typography;

interface ConfigItem {
  key: string;
  value: string;
  description: string;
  is_secret?: boolean;
}

const CONFIG_LABELS: Record<string, { label: string; placeholder: string; group: string; secret?: boolean }> = {
  llm_model: {
    label: 'Task Pipeline Model',
    placeholder: 'e.g. qwen2.5-7b-instruct',
    group: 'LLM Models',
  },
  chat_model: {
    label: 'Chat / Agent Model',
    placeholder: 'e.g. qwen3-max',
    group: 'LLM Models',
  },
  vl_model: {
    label: 'Vision-Language Model (Slide OCR)',
    placeholder: 'e.g. qwen2.5-vl-72b-instruct',
    group: 'LLM Models',
  },
  llm_api_base: {
    label: 'API Base URL',
    placeholder: 'e.g. https://dashscope.aliyuncs.com/compatible-mode/v1',
    group: 'API Provider',
  },
  dashscope_api_key: {
    label: 'DashScope API Key',
    placeholder: 'sk-xxxxxxxxxxxxxxxxxxxxxxxx',
    group: 'API Provider',
    secret: true,
  },
  cos_secret_id: {
    label: 'COS Secret ID',
    placeholder: 'AKIDxxxxxxxxxxxxxxxxxxxxxxxx',
    group: 'Tencent COS (Object Storage)',
    secret: true,
  },
  cos_secret_key: {
    label: 'COS Secret Key',
    placeholder: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    group: 'Tencent COS (Object Storage)',
    secret: true,
  },
  cos_region: {
    label: 'COS Region',
    placeholder: 'e.g. ap-guangzhou',
    group: 'Tencent COS (Object Storage)',
  },
  cos_bucket: {
    label: 'COS Bucket',
    placeholder: 'e.g. my-bucket-1250000000',
    group: 'Tencent COS (Object Storage)',
  },
};

const SettingsPage: React.FC = () => {
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_PREFIX}/api/config/`);
      if (!res.ok) throw new Error('Failed to fetch config');
      const data: ConfigItem[] = await res.json();
      setConfigs(data);
      // Set form values
      const formValues: Record<string, string> = {};
      data.forEach((item) => {
        formValues[item.key] = item.value;
      });
      form.setFieldsValue(formValues);
    } catch (error) {
      console.error('Error fetching config:', error);
      message.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const handleSave = async (values: Record<string, string>) => {
    setSaving(true);
    try {
      const updates = Object.entries(values)
        .filter(([key, value]) => {
          if (value === undefined || value === null) return false;
          const trimmed = value.trim();
          // Skip masked secret values (unchanged) — they look like "****" or "***xxxx"
          if (trimmed.length > 0 && /^\*+/.test(trimmed)) return false;
          return true;
        })
        .map(([key, value]) => ({
          key,
          value: value.trim(),
        }));

      const res = await fetch(`${API_PREFIX}/api/config/update/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });

      if (!res.ok) throw new Error('Failed to save config');
      const data = await res.json();
      message.success(`${data.count} setting(s) updated successfully`);
      await fetchConfigs();
    } catch (error) {
      console.error('Error saving config:', error);
      message.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spin size="large" />
      </div>
    );
  }

  // Group configs
  const groups: Record<string, string[]> = {};
  Object.entries(CONFIG_LABELS).forEach(([key, info]) => {
    if (!groups[info.group]) groups[info.group] = [];
    groups[info.group].push(key);
  });

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <Title level={3}>Settings</Title>
        <Text type="secondary">
          Configure model providers and other system settings. Changes take effect immediately for new tasks and chat sessions.
        </Text>
      </div>

      <Form form={form} layout="vertical" onFinish={handleSave}>
        {Object.entries(groups).map(([groupName, keys]) => (
          <Card
            key={groupName}
            title={groupName}
            className="mb-4 shadow-sm"
            size="small"
          >
            {keys.map((key) => {
              const label = CONFIG_LABELS[key];
              const currentConfig = configs.find((c) => c.key === key);
              return (
                <Form.Item
                  key={key}
                  name={key}
                  label={
                    <div className="flex items-center gap-2">
                      <span>{label?.label || key}</span>
                      {currentConfig?.description && (
                        <Tag color="default" className="text-xs">
                          {currentConfig.description}
                        </Tag>
                      )}
                    </div>
                  }
                >
                    {label?.secret ? (
                    <Input.Password
                      placeholder={label?.placeholder || ''}
                      allowClear
                      visibilityToggle
                    />
                  ) : (
                    <Input
                      placeholder={label?.placeholder || ''}
                      allowClear
                    />
                  )}
                </Form.Item>
              );
            })}
          </Card>
        ))}

        {/* Show any configs that don't match known labels */}
        {configs.filter((c) => !CONFIG_LABELS[c.key]).length > 0 && (
          <Card title="Other" className="mb-4 shadow-sm" size="small">
            {configs
              .filter((c) => !CONFIG_LABELS[c.key])
              .map((config) => (
                <Form.Item
                  key={config.key}
                  name={config.key}
                  label={
                    <div className="flex items-center gap-2">
                      <span>{config.key}</span>
                      {config.description && (
                        <Tag color="default" className="text-xs">
                          {config.description}
                        </Tag>
                      )}
                    </div>
                  }
                >
                  <Input allowClear />
                </Form.Item>
              ))}
          </Card>
        )}

        <div className="flex gap-3">
          <Button
            type="primary"
            htmlType="submit"
            icon={<SaveOutlined />}
            loading={saving}
            size="large"
          >
            Save Settings
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchConfigs}
            size="large"
          >
            Reset
          </Button>
        </div>
      </Form>
    </div>
  );
};

export default SettingsPage;
