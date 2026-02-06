
import { useState, useRef, useEffect } from 'react';
import { Card, Spin, List } from 'antd';
import { API_PREFIX } from '../../config';
import { TranscriptData } from '../../model'

// Helper function to format milliseconds to mm:ss
const formatTime = (milliseconds: number): string => {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};


interface LectureTranscriptsProps {
  videoId?: string;
  handleItemClick : (time : number) => void,
  height?: string | number; // Allow custom height
}

const LectureTranscripts: React.FC<LectureTranscriptsProps> = ({
  videoId,
  handleItemClick,
  height = '200px'
}) => {

  const [transcriptData, setTranscriptData] = useState<TranscriptData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Fetch video transcripts
  useEffect(() => {
    const fetchTranscripts = async () => {
        try {
            const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/transcript`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data : TranscriptData = await response.json();
            setTranscriptData(data);
            setLoading(false);
        } catch (error) {
            console.error("Failed to fetch transcripts:", error);
        }
    };
    
    fetchTranscripts();
  }, [videoId]);


  return (
    <div>
      <Spin spinning={loading}>
        <div 
          className="transcript-list-container"
        >
          <List
            dataSource={transcriptData?.sentences || []}
            renderItem={(sentence) => (
              <List.Item
                key={sentence.sentence_id}
                className="transcript-sentence-item"
                onClick={() => handleItemClick(sentence.begin_time / 1000)}
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
                  <span className="text-gray-500 font-mono text-sm min-w-[40px]">
                    {formatTime(sentence.begin_time)}
                  </span>
                  {/* Sentence text */}
                  <span className="text-gray-800 flex-1">
                    {sentence.text}
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

export default LectureTranscripts;
