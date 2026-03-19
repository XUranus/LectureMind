import { useState, useEffect, useRef, useCallback } from 'react';
import { Spin, Collapse, Tag, Empty, Badge, Tooltip } from 'antd';
import {
  BulbOutlined,
  ClockCircleOutlined,
  TagsOutlined,
  StarFilled,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { SectionWithKnowledge, KnowledgePoint } from '../../model';

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

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
  isActive?: boolean;
}

const KnowledgePointCard: React.FC<KnowledgePointCardProps> = ({ kp, handleTimeClick, isActive }) => (
  <div
    className={`border rounded-lg p-3 mb-2 transition-all duration-200 ${
      isActive
        ? 'bg-blue-50 border-blue-300 shadow-sm'
        : 'bg-white border-gray-100 hover:shadow-sm'
    }`}
  >
    <div className="flex items-start justify-between gap-2 mb-1">
      <div className="flex items-center gap-2 flex-1">
        <BulbOutlined className={`flex-shrink-0 mt-0.5 ${isActive ? 'text-blue-500' : 'text-yellow-500'}`} />
        <span className={`font-medium text-sm ${isActive ? 'text-blue-900' : 'text-gray-900'}`}>
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
    <p className="text-gray-600 text-sm mb-2 ml-6">{kp.summary}</p>
    <div className="flex flex-wrap items-center gap-1 ml-6">
      {kp.key_terms && kp.key_terms.length > 0 && (
        <>
          <TagsOutlined className="text-gray-400 text-xs" />
          {kp.key_terms.map((term, idx) => (
            <Tag key={idx} className="m-0 text-xs" color="geekblue">{term}</Tag>
          ))}
        </>
      )}
      <span
        className={`text-xs cursor-pointer ml-auto ${isActive ? 'text-blue-500 font-medium' : 'text-gray-400 hover:text-blue-500'}`}
        onClick={() => handleTimeClick(kp.begin_time)}
      >
        <ClockCircleOutlined className="mr-1" />
        {formatTime(kp.begin_time)}
      </span>
    </div>
  </div>
);

interface LectureKnowledgeProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  currentTime?: number;
}

const LectureKnowledge: React.FC<LectureKnowledgeProps> = ({
  videoId,
  handleItemClick,
  currentTime = 0,
}) => {
  const [data, setData] = useState<SectionWithKnowledge[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const activeKpRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const fetchKnowledge = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/knowledge/grouped/`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
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
    if (videoId) fetchKnowledge();
  }, [videoId]);

  const handleScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => { userScrolling.current = false; }, 3000);
  }, []);

  // Find active section and active knowledge point
  const activeSection = data?.find(
    (s) => currentTime >= s.begin_time && currentTime < s.end_time
  );
  const activeKpId = activeSection?.knowledge_points?.find(
    (kp) => currentTime >= kp.begin_time && currentTime < kp.end_time
  )?.id;

  useEffect(() => {
    if (activeKpRef.current && !userScrolling.current) {
      activeKpRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeKpId]);

  const totalKP = data
    ? data.reduce((sum, s) => sum + (s.knowledge_points?.length || 0), 0)
    : 0;

  return (
    <div className="flex flex-col h-full" onScroll={handleScroll}>
      <Spin spinning={loading}>
        {error ? (
          <Empty description="No knowledge points available yet. Process the video to extract knowledge." />
        ) : data && data.length > 0 ? (
          <div className="flex flex-col h-full">
            <div className="flex items-center gap-3 mb-3 px-1">
              <Badge count={totalKP} showZero color="blue" overflowCount={999} />
              <span className="text-gray-500 text-sm">
                knowledge points across {data.length} section{data.length !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto">
              <Collapse
                defaultActiveKey={data.map((_, i) => String(i))}
                ghost
                items={data.map((section, idx) => {
                  const isSectionActive = currentTime >= section.begin_time && currentTime < section.end_time;
                  return {
                    key: String(idx),
                    label: (
                      <div className="flex items-center gap-2">
                        <Tag color={isSectionActive ? 'blue' : 'default'} className="m-0">
                          <ClockCircleOutlined className="mr-1" />
                          {formatTime(section.begin_time)} - {formatTime(section.end_time)}
                        </Tag>
                        <span className={`font-medium ${isSectionActive ? 'text-blue-900' : 'text-gray-900'}`}>
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
                          section.knowledge_points.map((kp) => {
                            const isKpActive = kp.id === activeKpId;
                            return (
                              <div key={kp.id} ref={isKpActive ? activeKpRef : undefined}>
                                <KnowledgePointCard
                                  kp={kp}
                                  handleTimeClick={handleItemClick}
                                  isActive={isKpActive}
                                />
                              </div>
                            );
                          })
                        ) : (
                          <p className="text-gray-400 text-sm italic">
                            No knowledge points extracted for this section.
                          </p>
                        )}
                      </div>
                    ),
                  };
                })}
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
