import { useState, useEffect } from 'react';
import { Spin, Collapse, Tag, Empty, Badge, Tooltip } from 'antd';
import {
  BulbOutlined,
  ClockCircleOutlined,
  TagsOutlined,
  StarFilled,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { SectionWithKnowledge, KnowledgePoint } from '../../model';

// Helper: format seconds to mm:ss
const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

// Helper: importance to color
const importanceColor = (importance: number): string => {
  if (importance >= 0.8) return 'red';
  if (importance >= 0.6) return 'orange';
  if (importance >= 0.4) return 'blue';
  return 'default';
};

const importanceLabel = (importance: number): string => {
  if (importance >= 0.8) return 'Core';
  if (importance >= 0.6) return 'Important';
  if (importance >= 0.4) return 'Relevant';
  return 'Supplementary';
};


interface KnowledgePointCardProps {
  kp: KnowledgePoint;
  handleTimeClick: (time: number) => void;
}

const KnowledgePointCard: React.FC<KnowledgePointCardProps> = ({ kp, handleTimeClick }) => {
  return (
    <div
      className="bg-white border border-gray-100 rounded-lg p-3 mb-2 hover:shadow-sm transition-shadow"
    >
      {/* Title row */}
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 flex-1">
          <BulbOutlined className="text-yellow-500 flex-shrink-0 mt-0.5" />
          <span className="font-medium text-gray-900 text-sm">
            {kp.title}
          </span>
        </div>
        <Tooltip title={`Importance: ${importanceLabel(kp.importance)}`}>
          <Tag color={importanceColor(kp.importance)} className="m-0 flex-shrink-0">
            <StarFilled className="mr-1" style={{ fontSize: 10 }} />
            {importanceLabel(kp.importance)}
          </Tag>
        </Tooltip>
      </div>

      {/* Summary */}
      <p className="text-gray-600 text-sm mb-2 ml-6">
        {kp.summary}
      </p>

      {/* Key terms + time */}
      <div className="flex flex-wrap items-center gap-1 ml-6">
        {kp.key_terms && kp.key_terms.length > 0 && (
          <>
            <TagsOutlined className="text-gray-400 text-xs" />
            {kp.key_terms.map((term, idx) => (
              <Tag key={idx} className="m-0 text-xs" color="geekblue">
                {term}
              </Tag>
            ))}
          </>
        )}
        <span
          className="text-gray-400 text-xs cursor-pointer hover:text-blue-500 ml-auto"
          onClick={() => handleTimeClick(kp.begin_time)}
        >
          <ClockCircleOutlined className="mr-1" />
          {formatTime(kp.begin_time)}
        </span>
      </div>
    </div>
  );
};


interface LectureKnowledgeProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
}

const LectureKnowledge: React.FC<LectureKnowledgeProps> = ({
  videoId,
  handleItemClick,
}) => {
  const [data, setData] = useState<SectionWithKnowledge[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchKnowledge = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `${API_PREFIX}/api/videos/${videoId}/knowledge/grouped/`
        );
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const result: SectionWithKnowledge[] = await response.json();
        setData(result);
      } catch (err: any) {
        console.error('Failed to fetch knowledge:', err);
        setError(err.message || 'Failed to load knowledge');
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    if (videoId) {
      fetchKnowledge();
    }
  }, [videoId]);

  // Count total knowledge points
  const totalKP = data
    ? data.reduce((sum, s) => sum + (s.knowledge_points?.length || 0), 0)
    : 0;

  return (
    <div className="flex flex-col h-full">
      <Spin spinning={loading}>
        {error ? (
          <Empty
            description="No knowledge points available yet. Process the video to extract knowledge."
          />
        ) : data && data.length > 0 ? (
          <div className="flex flex-col h-full">
            {/* Stats bar */}
            <div className="flex items-center gap-3 mb-3 px-1">
              <Badge
                count={totalKP}
                showZero
                color="blue"
                overflowCount={999}
              />
              <span className="text-gray-500 text-sm">
                knowledge points across {data.length} section{data.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Collapsible sections */}
            <div className="flex-1 overflow-y-auto">
              <Collapse
                defaultActiveKey={data.map((_, i) => String(i))}
                ghost
                items={data.map((section, idx) => ({
                  key: String(idx),
                  label: (
                    <div className="flex items-center gap-2">
                      <Tag color="blue" className="m-0">
                        <ClockCircleOutlined className="mr-1" />
                        {formatTime(section.begin_time)} - {formatTime(section.end_time)}
                      </Tag>
                      <span className="font-medium text-gray-900">
                        {section.title || `Section ${section.order + 1}`}
                      </span>
                      <Badge
                        count={section.knowledge_points?.length || 0}
                        showZero
                        color="gray"
                        className="ml-auto"
                      />
                    </div>
                  ),
                  children: (
                    <div className="pl-1">
                      {section.knowledge_points && section.knowledge_points.length > 0 ? (
                        section.knowledge_points.map((kp) => (
                          <KnowledgePointCard
                            key={kp.id}
                            kp={kp}
                            handleTimeClick={handleItemClick}
                          />
                        ))
                      ) : (
                        <p className="text-gray-400 text-sm italic">
                          No knowledge points extracted for this section.
                        </p>
                      )}
                    </div>
                  ),
                }))}
              />
            </div>
          </div>
        ) : (
          <Empty description="No knowledge points available" />
        )}
      </Spin>
    </div>
  );
};

export default LectureKnowledge;
