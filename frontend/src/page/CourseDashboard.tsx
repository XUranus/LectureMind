import React, { useState, useEffect } from 'react';
import { Card, message, Modal, Button, Input, Form } from 'antd';
import { useNavigate } from 'react-router-dom';
import { API_PREFIX } from '../config';
import CourseCreationModal from '../components/lecture/CourseCreationModal';
import { DeleteOutlined, MessageOutlined, EditOutlined } from '@ant-design/icons';
import { Course } from '../model';

const DEFAULT_COVER = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170" viewBox="0 0 300 170"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="16" fill="%23999">No Cover</text></svg>`;

const CourseDashboard: React.FC = () => {
  const [courses, setCourses] = useState<Course[]>([]);

  useEffect(() => {
    const fetchCourses = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/episodes`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data: Course[] = await response.json();
        setCourses(data);
      } catch (error) {
        console.error('Failed to fetch courses:', error);
      }
    };
    fetchCourses();
  }, []);

  const addCourse = (course: Course) => {
    setCourses(prev => [...prev, course]);
  };

  const deleteCourse = (id: string) => {
    setCourses(prev => prev.filter(c => c.id !== id));
  };

  const updateCourse = (id: string, updates: Partial<Course>) => {
    setCourses(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Courses</h1>
        <CourseCreationModal addCourse={addCourse} />
      </div>
      {courses.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          No courses yet. Create one to get started.
        </div>
      ) : (
        courses.map((episode) => (
          <CourseCard
            key={episode.id}
            episode={episode}
            onDeleted={deleteCourse}
            onUpdated={updateCourse}
          />
        ))
      )}
    </div>
  );
};

// Course Edit Modal
const CourseEditModal: React.FC<{
  course: Course;
  open: boolean;
  onCancel: () => void;
  onSaved: (id: string, updates: Partial<Course>) => void;
}> = ({ course, open, onCancel, onSaved }) => {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      form.setFieldsValue({ title: course.title, description: course.description });
    }
  }, [open, course, form]);

  const handleSave = async (values: { title: string; description: string }) => {
    setSaving(true);
    try {
      const response = await fetch(`${API_PREFIX}/api/episodes/update/${course.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: values.title, description: values.description }),
      });
      if (!response.ok) throw new Error('Failed to update course');
      onSaved(course.id, { title: values.title, description: values.description });
      message.success('Course updated successfully');
      onCancel();
    } catch (err) {
      console.error('Failed to update course:', err);
      message.error('Failed to update course');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Edit Course" open={open} onCancel={onCancel} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={handleSave}>
        <Form.Item
          name="title"
          label="Title"
          rules={[{ required: true, message: 'Title is required' }, { max: 100 }]}
        >
          <Input />
        </Form.Item>
        <Form.Item name="description" label="Description" rules={[{ max: 500 }]}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button type="primary" htmlType="submit" loading={saving}>Save</Button>
        </div>
      </Form>
    </Modal>
  );
};

// Single Course Card
const CourseCard: React.FC<{
  episode: Course;
  onDeleted: (id: string) => void;
  onUpdated: (id: string, updates: Partial<Course>) => void;
}> = ({ episode, onDeleted, onUpdated }) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const displayVideos = expanded ? episode.videos : episode.videos.slice(0, 10);

  const handleDelete = () => {
    Modal.confirm({
      title: 'Are you sure?',
      content: `Delete course "${episode.title}"? This action cannot be undone.`,
      okText: 'Yes, Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      centered: true,
      onOk: async () => {
        setDeleting(true);
        try {
          const response = await fetch(`${API_PREFIX}/api/episodes/delete/${episode.id}`, {
            method: 'DELETE',
          });
          if (response.ok) {
            message.success('Course deleted successfully');
            onDeleted(episode.id);
          } else {
            message.error('Failed to delete course');
          }
        } catch (err) {
          console.error('Network error:', err);
          message.error('Network error. Please try again.');
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  return (
    <>
      <Card
        title={
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold m-0">{episode.title}</h2>
            <span className="text-sm text-gray-400 font-normal">
              {episode.videos.length} video{episode.videos.length !== 1 ? 's' : ''}
            </span>
          </div>
        }
        className="shadow-md rounded-lg"
        extra={
          <div className="flex items-center gap-2">
            <Button
              type="primary"
              icon={<MessageOutlined />}
              onClick={() => navigate(`/courses/${episode.id}`)}
              size="small"
            >
              Chat
            </Button>
            <Button
              icon={<EditOutlined />}
              onClick={() => setEditOpen(true)}
              size="small"
            >
              Edit
            </Button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-red-500 hover:text-red-700 transition-colors p-1"
              aria-label="Delete course"
            >
              <DeleteOutlined style={{ fontSize: '16px' }} />
            </button>
          </div>
        }
      >
        {episode.description && (
          <p className="text-gray-600 mb-3">{episode.description}</p>
        )}
        <p className="text-xs text-gray-400 mb-3">
          Created: {new Date(episode.created_at).toLocaleDateString()}
        </p>

        {/* Video thumbnails */}
        <div className="overflow-x-auto pb-2 scrollbar-hide">
          <div className="flex space-x-3 min-w-max p-1">
            {displayVideos.map((video) => (
              <div
                key={video.id}
                className="flex-shrink-0 w-28 h-20 relative group cursor-pointer"
                onClick={() => navigate(`/lecture/${video.id}`)}
              >
                <img
                  src={video.cover_url ?? DEFAULT_COVER}
                  alt={video.title}
                  className="w-full h-full object-cover rounded border border-gray-200"
                />
                <div className="absolute inset-0 bg-black bg-opacity-50 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <span className="text-white text-xs text-center px-1 line-clamp-2">{video.title}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {episode.videos.length > 10 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-blue-600 hover:text-blue-800 text-sm font-medium"
          >
            {expanded ? 'Show less' : `Show all ${episode.videos.length} videos`}
          </button>
        )}
      </Card>

      <CourseEditModal
        course={episode}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onSaved={onUpdated}
      />
    </>
  );
};

export default CourseDashboard;
