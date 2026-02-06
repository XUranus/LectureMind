
import { useState, useRef, useEffect } from 'react';
import { Card, Spin, List } from 'antd';
import { API_PREFIX } from '../../config';
import { Section } from '../../model'


interface LectureSectionsProps {
  videoId?: string;
  handleItemClick : (time : number) => void,
  height?: string | number; // Allow custom height
}

const LectureSections: React.FC<LectureSectionsProps> = ({
  videoId,
  handleItemClick,
  height = '200px'
}) => {

  const [sections, setSections] = useState<Section[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Fetch video sections
  useEffect(() => {
    const fetchSections = async () => {
        try {
            const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/sections`);
            // if (!response.ok) {
            //     throw new Error(`HTTP error! status: ${response.status}`);
            // }
            // const data : Section[] = await response.json();
            // TODO: Use mock data for now
            const data : Section[] = [
              { id: 1, begin_time: 0, text: "Introduction to the lecture and overview of topics." },
              { id: 2, begin_time: 300, text: "Deep dive into the first topic with examples." },
              { id: 3, begin_time: 900, text: "Discussion on advanced concepts and applications." },
              { id: 4, begin_time: 1500, text: "Summary and conclusion of the lecture." }
            ]

            setSections(data);
            setLoading(false);
        } catch (error) {
            console.error("Failed to fetch sections:", error);
        }
    };
    
    fetchSections();
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
          <List
            dataSource={sections || []}
            renderItem={(section) => (
              <List.Item
                key={section.id}
                className="transcript-sentence-item"
                onClick={() => handleItemClick(section.begin_time / 1000)}
                style={{
                  padding: '12px 16px',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s ease',
                  borderBottom: '1px solid #f0f0f0'
                }}
                // Hover effect using inline styles (or you can use Tailwind classes)
                onMouseEnter={(e) => {
                  (e.target as HTMLElement).style.backgroundColor = '#f5f5f5';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLElement).style.backgroundColor = 'transparent';
                }}
              >
                <div className="flex items-start gap-3">
                  {/* Timestamp */}
                  {/* Sentence text */}
                  <span className="text-gray-800 flex-1">
                    {section.text}
                  </span>
                </div>
              </List.Item>
            )}
            locale={{ emptyText: 'No transcript available' }}
          />
        </div>
      </Spin>
    </div>
  );
};

export default LectureSections;
