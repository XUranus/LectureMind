import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Spin, Button, Tag } from 'antd';
import { ArrowLeftOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { API_PREFIX } from '../config';
import { Course } from '../model';
import CourseChatbot from '../components/lecture/CourseChatbot';

const DEFAULT_COVER = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170" viewBox="0 0 300 170"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="16" fill="%23999">No Cover</text></svg>`;

const CourseDetailPage: React.FC = () => {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCourse = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/episodes/${courseId}/`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data: Course = await response.json();
        setCourse(data);
      } catch (error) {
        console.error('Failed to fetch course:', error);
      } finally {
        setLoading(false);
      }
    };
    if (courseId) fetchCourse();
  }, [courseId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500 mb-4">Course not found</p>
        <Button onClick={() => navigate('/courses')}>Back to Courses</Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4" style={{ height: 'calc(100vh - 100px)' }}>
      {/* Left: Course info + video list */}
      <div className="lg:w-2/5 flex flex-col overflow-hidden">
        <div className="shrink-0 mb-4">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/courses')}
            className="mb-2"
          >
            Back to Courses
          </Button>
          <h1 className="text-2xl font-bold text-gray-800">{course.title}</h1>
          {course.description && (
            <p className="text-gray-500 mt-1">{course.description}</p>
          )}
          <div className="flex items-center gap-2 mt-2">
            <Tag icon={<VideoCameraOutlined />} color="blue">
              {course.videos.length} video{course.videos.length !== 1 ? 's' : ''}
            </Tag>
            <span className="text-xs text-gray-400">
              Created {new Date(course.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>

        {/* Video list */}
        <div className="flex-1 overflow-y-auto">
          <h3 className="text-sm font-medium text-gray-500 mb-2 px-1">Lectures</h3>
          <div className="space-y-2">
            {course.videos.map((video, index) => (
              <div
                key={video.id}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 cursor-pointer transition-colors"
                onClick={() => navigate(`/lecture/${video.id}`)}
              >
                <div className="w-20 h-14 flex-shrink-0 rounded overflow-hidden bg-gray-200">
                  <img
                    src={video.cover.length === 0 ? DEFAULT_COVER : video.cover}
                    alt={video.title}
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {index + 1}. {video.title}
                  </p>
                  {video.duration > 0 && (
                    <p className="text-xs text-gray-400">
                      {Math.floor(video.duration / 60)}:{Math.floor(video.duration % 60).toString().padStart(2, '0')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right: Course chatbot */}
      <div className="lg:w-3/5 flex flex-col min-h-0 border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
        <CourseChatbot courseId={courseId || ''} courseTitle={course.title} />
      </div>
    </div>
  );
};

export default CourseDetailPage;
