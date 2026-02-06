
import { useState, useRef, useEffect } from 'react';
import { Button, Spin, Tabs } from 'antd';
import {} from '../../model'

interface LectureChatBotProps {
  videoId: string | undefined;
}

const LectureChatBot: React.FC<LectureChatBotProps> = ({ videoId }) => {
  const [chatMessages, setChatMessages] = useState<{id: number; text: string; sender: 'user' | 'agent'}[]>([]);
  const [inputValue, setInputValue] = useState('');

  const addAgentMessage = (text: string) => {
    setChatMessages(prev => [
      ...prev,
      { id: Date.now(), text, sender: 'agent' }
    ]);
  };

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;
    
    // Add user message
    setChatMessages(prev => [
      ...prev,
      { id: Date.now(), text: inputValue, sender: 'user' }
    ]);
    
    // Clear input
    setInputValue('');
    
    // Simulate agent response after delay
    setTimeout(() => {
      addAgentMessage(`I received your query: "${inputValue}". Here's what I found...`);
    }, 1000);
  };


  // Fetch video + thumbnails
  // useEffect(() => {
  //   const fetchData = async () => {
  //     try {
  //       const [videoRes, thumbsRes] = await Promise.all([
  //         fetch(`/api/videos/${videoId}/`),
  //         fetch(`/api/videos/${videoId}/thumbnails/`)
  //       ]);
  //       const video = await videoRes.json();
  //       const thumbnails = await thumbsRes.json();
  //       setVideoData({ ...video, thumbnails });
  //     } catch (err) {
  //       message.error('Failed to load video resources');
  //     } finally {
  //       setLoading(false);
  //     }
  //   };
  //   fetchData();
  // }, [videoId]);


  return (
    <div className="flex flex-col h-full">
      {/* Scrollable message area */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50 space-y-4">
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                msg.sender === 'user'
                  ? 'bg-blue-500 text-white rounded-tr-none'
                  : 'bg-gray-200 text-gray-800 rounded-tl-none'
              }`}
            >
              {msg.text}
            </div>
          </div>
        ))}
      </div>

      {/* Fixed input area at bottom */}
      <div className="shrink-0 p-4 border-t border-gray-200 bg-white">
        <div className="flex">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask about the video..."
            className="flex-1 border border-gray-300 rounded-l-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          />
          <Button
            type="primary"
            onClick={handleSendMessage}
            disabled={!inputValue.trim()}
            className="rounded-r-lg"
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

export default LectureChatBot;