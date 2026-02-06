// CourseCreationModal.tsx
import React, { useState } from 'react';
import { Button, Modal, Form, Input, Spin, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { Course } from '../../model';


export interface CourseCreationModalProps {
    addCourse : (course : Course) => void
}

const CourseCreationModal: React.FC<CourseCreationModalProps> = ({addCourse}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<Course>();

  const showModal = () => {
    setIsModalOpen(true);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    form.resetFields();
  };

  const createCourseAPI = async (course : Course) => {
    console.log('new course: ', course)
    try {
        const response = await fetch(`${API_PREFIX}/api/episodes/new/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(course), // Convert JS object to JSON string
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data : Course = await response.json();
        console.log('new course: ', data)
        addCourse(data)
    } catch (error) {
        console.error("Failed to fetch slides thumbs:", error);
    }
  }

  const onFinish = async (values: Course) => {
    setLoading(true);
    try {
      // 👇 Replace this with your actual API call
      await createCourseAPI(values);

      message.success('Course created successfully!');
      form.resetFields();
      setIsModalOpen(false);
      
      // Optional: trigger refetch of course list here
    } catch (error) {
      console.error('Failed to create course:', error);
      message.error('Failed to create course. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Button type="primary" icon={<PlusOutlined />} onClick={showModal}>
        Create New Course
      </Button>

      <Modal
        title="Create New Course"
        open={isModalOpen}
        onCancel={handleCancel}
        footer={null}
        destroyOnHidden
      >
        <Spin spinning={loading}>
          <Form
            form={form}
            layout="vertical"
            onFinish={onFinish}
            autoComplete="off"
          >
            <Form.Item
              name="title"
              label="Title"
              rules={[
                { required: true, message: 'Please enter a course title!' },
                { max: 100, message: 'Title must be at most 100 characters.' }
              ]}
            >
              <Input placeholder="e.g. Introduction to React" />
            </Form.Item>

            <Form.Item
              name="description"
              label="Description"
              rules={[{ max: 500, message: 'Description must be at most 500 characters.' }]}
            >
              <Input.TextArea
                rows={4}
                placeholder="Briefly describe what this course covers..."
              />
            </Form.Item>

            <div className="flex justify-end gap-2">
              <Button onClick={handleCancel} disabled={loading}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={loading}>
                Create Course
              </Button>
            </div>
          </Form>
        </Spin>
      </Modal>
    </>
  );
};

export default CourseCreationModal;