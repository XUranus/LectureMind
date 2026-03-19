import { useState, useEffect } from 'react';
import { Spin, Tag, Empty, Divider } from 'antd';
import {
  BookOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { KnowledgeSummaryData } from '../../model';

const difficultyColors: Record<string, string> = {
  beginner: 'green',
  intermediate: 'orange',
  advanced: 'red',
};

interface LectureSummaryProps {
  videoId?: string;
}

const LectureSummary: React.FC<LectureSummaryProps> = ({ videoId }) => {
  const [summary, setSummary] = useState<KnowledgeSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/summary/`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data: KnowledgeSummaryData = await response.json();
        setSummary(data);
      } catch (err: any) {
        setError(err.message);
        setSummary(null);
      } finally {
        setLoading(false);
      }
    };
    if (videoId) fetchSummary();
  }, [videoId]);

  return (
    <div className="flex flex-col h-full">
      <Spin spinning={loading}>
        {error || !summary ? (
          <Empty description="No summary available yet. Process the video to generate a summary." />
        ) : (
          <div className="space-y-4">
            {/* Difficulty badge */}
            {summary.difficulty_level && (
              <div className="flex items-center gap-2">
                <BarChartOutlined className="text-gray-500" />
                <span className="text-gray-500 text-sm">Difficulty:</span>
                <Tag color={difficultyColors[summary.difficulty_level] || 'default'}>
                  {summary.difficulty_level.charAt(0).toUpperCase() + summary.difficulty_level.slice(1)}
                </Tag>
              </div>
            )}

            {/* Overview */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <BookOutlined className="text-blue-500" />
                <span className="font-semibold text-gray-900">Overview</span>
              </div>
              <p className="text-gray-700 text-sm leading-relaxed pl-6">
                {summary.overview}
              </p>
            </div>

            <Divider className="my-2" />

            {/* Key Topics */}
            {summary.key_topics && summary.key_topics.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <BulbOutlined className="text-yellow-500" />
                  <span className="font-semibold text-gray-900">Key Topics</span>
                </div>
                <div className="flex flex-wrap gap-2 pl-6">
                  {summary.key_topics.map((topic, i) => (
                    <Tag key={i} color="blue">{topic}</Tag>
                  ))}
                </div>
              </div>
            )}

            {/* Learning Objectives */}
            {summary.learning_objectives && summary.learning_objectives.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircleOutlined className="text-green-500" />
                  <span className="font-semibold text-gray-900">Learning Objectives</span>
                </div>
                <ul className="list-disc list-inside pl-6 space-y-1">
                  {summary.learning_objectives.map((obj, i) => (
                    <li key={i} className="text-gray-700 text-sm">{obj}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Prerequisites */}
            {summary.prerequisites && summary.prerequisites.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <InfoCircleOutlined className="text-orange-500" />
                  <span className="font-semibold text-gray-900">Prerequisites</span>
                </div>
                <div className="flex flex-wrap gap-2 pl-6">
                  {summary.prerequisites.map((prereq, i) => (
                    <Tag key={i} color="orange">{prereq}</Tag>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Spin>
    </div>
  );
};

export default LectureSummary;
