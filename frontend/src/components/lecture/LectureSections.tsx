
import { useState, useEffect } from 'react';
import { Spin, List, Tag, Empty } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { Section } from '../../model'


// Helper: format seconds to mm:ss
const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};


interface LectureSectionsProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  height?: string | number;
}

const LectureSections: React.FC<LectureSectionsProps> = ({
  videoId,
  handleItemClick,
  height = '200px'
}) => {

  const [sections, setSections] = useState<Section[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch video sections from the API
  useEffect(() => {
    const fetchSections = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/sections/`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data: Section[] = await response.json();
        setSections(data);
      } catch (err: any) {
        console.error("Failed to fetch sections:", err);
        setError(err.message || "Failed to load sections");
        setSections([]);
      } finally {
        setLoading(false);
      }
    };

    if (videoId) {
      fetchSections();
    }
  }, [videoId]);


  return (
    <div>
      <Spin spinning={loading}>
        <div
          className="transcript-list-container"
          style={{
            height: '100%',
            overflowY: 'auto',
            overflowX: 'hidden'
          }}
        >
          {error ? (
            <Empty
              description={`No sections available yet. Process the video to generate sections.`}
            />
          ) : (
            <List
              dataSource={sections || []}
              renderItem={(section) => (
                <List.Item
                  key={section.id}
                  className="transcript-sentence-item"
                  onClick={() => handleItemClick(section.begin_time)}
                  style={{
                    padding: '12px 16px',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s ease',
                    borderBottom: '1px solid #f0f0f0'
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.backgroundColor = '#f5f5f5';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent';
                  }}
                >
                  <div className="flex flex-col gap-1 w-full">
                    {/* Header: title + time range */}
                    <div className="flex items-center gap-2">
                      <Tag color="blue" className="m-0">
                        <ClockCircleOutlined className="mr-1" />
                        {formatTime(section.begin_time)} - {formatTime(section.end_time)}
                      </Tag>
                      <span className="font-medium text-gray-900">
                        {section.title}
                      </span>
                    </div>
                    {/* Transcript preview */}
                    {section.transcript_text && (
                      <span className="text-gray-500 text-sm line-clamp-2">
                        {section.transcript_text.substring(0, 200)}
                        {section.transcript_text.length > 200 ? '...' : ''}
                      </span>
                    )}
                  </div>
                </List.Item>
              )}
              locale={{ emptyText: 'No sections available' }}
            />
          )}
        </div>
      </Spin>
    </div>
  );
};

export default LectureSections;
