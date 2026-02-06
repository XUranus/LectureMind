import React, { useState, useRef, Dispatch, SetStateAction, useEffect } from 'react';
import { Button, message, Select, Spin } from 'antd';
import {
  VideoCameraOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { RcFile } from 'antd/es/upload';
import { v4 as uuidv4 } from 'uuid';
import { API_PREFIX } from '../config';

import { Course } from '../model'


interface UploadDashboardProps {
  setUploadProgress: Dispatch<SetStateAction<number>>;
}

const UploadDashboard: React.FC<UploadDashboardProps> = ({ setUploadProgress }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [unnerUploadProgress, setInnerUploadProgress] = useState(0);
  const [inputValue, setInputValue] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setselectedCourseId] = useState<string>('');

  useEffect(() => {
    const fetchCourses = async () => {
        try {
            const response = await fetch(`${API_PREFIX}/api/episodes`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data : Course[] = await response.json();
            setCourses(data);
            console.log(data)
        } catch (error) {
            console.error("Failed to fetch slides thumbs:", error);
        }
    };
    
    fetchCourses();
  }, []);

  // Simulate "processing" after upload completes (e.g., backend analysis)
  const simulateProcessing = () => {
    setIsProcessing(true);
    setTimeout(() => {
      setIsProcessing(false);
      message.success('Video uploaded and ready for analysis!');
    }, 3000);
  };

  const requestTriggerAsyncTask = async (id : string) => {
    console.log('request trigger async video task, id', id)
    try {
        const response = await fetch(`${API_PREFIX}/api/videos/process/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({id}), // Convert JS object to JSON string
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data : Course = await response.json();
        console.log('triggered task: ', data)
    } catch (error) {
        console.error("Failed to fetch slides thumbs:", error);
    }
  }

  const uploadFileToServer = (file: RcFile) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name || 'Untitled Video');
    formData.append('episode', selectedCourseId)

    const xhr = new XMLHttpRequest();

    xhr.open('POST', `${API_PREFIX}/api/videos/upload/`);

    // Track upload progress
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100);
        setInnerUploadProgress(percentComplete);
        setUploadProgress(percentComplete);
      }
    };

    xhr.onload = () => {
      setIsUploading(false);
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          console.log('Upload successful:', response);
          requestTriggerAsyncTask(response['id'])
          simulateProcessing(); // Optional: show processing state
        } catch (e) {
          message.error('Invalid server response');
        }
      } else {
        message.error(`Upload failed: ${xhr.statusText}`);
      }
    };

    xhr.onerror = () => {
      setIsUploading(false);
      message.error('Network error during upload');
    };

    xhr.send(formData);
  };

  const createRcFile = (file: File): RcFile => {
    const rcFile = file as RcFile;
    rcFile.uid = uuidv4();
    return rcFile;
  };

  const handleUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('video/')) {
      message.error('Please upload a video file');
      return;
    }

    const rcFile = createRcFile(file);
    setIsUploading(true);
    setUploadProgress(0);
    uploadFileToServer(rcFile);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('video/')) {
      message.error('Please upload a video file');
      return;
    }

    const rcFile = createRcFile(file);
    setIsUploading(true);
    setUploadProgress(0);
    uploadFileToServer(rcFile);
  };

  const handleCourseSelectionChange = (value: string) => {
    console.log(`selected ${value}`);
    setselectedCourseId(value);
  };

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div
        className="w-full max-w-3xl border-2 border-dashed border-blue-400 rounded-2xl p-10 text-center bg-white shadow-lg transition-all hover:shadow-xl"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center justify-center">
          <div className="bg-blue-100 p-4 rounded-full mb-6">
            <VideoCameraOutlined className="text-blue-600 text-3xl" />
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">
            {isUploading ? 'Uploading...' : isProcessing ? 'Processing...' : 'Upload Your Video'}
          </h2>
          <p className="text-gray-600 mb-6">
            {isUploading
              ? 'Uploading your video...'
              : isProcessing
              ? 'Analyzing your video...'
              : 'Drag & drop your video here or click the button below'}
          </p>

          {isUploading && (
            <div className="w-full max-w-md mb-4">
              <Spin tip={`${unnerUploadProgress}% uploaded`} />
            </div>
          )}

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="video/*"
            className="hidden"
          />

          <Button
            type="primary"
            size="large"
            icon={<UploadOutlined />}
            onClick={handleUploadClick}
            disabled={isUploading || isProcessing}
            className="mb-6"
          >
            Select Video File
          </Button>

          <p className="text-gray-500 text-sm">Supported formats: MP4, MOV, AVI, MKV</p>
        </div>

        <br/>
        <span className="font-semibold text-gray-800 mb-4">Episode: </span>
        <Select
          defaultValue="Default"
          style={{ width: 120 }}
          onChange={handleCourseSelectionChange}
          options={courses.map((course : Course) => ({
            value : course.id,
            label : course.title
          }))}
        />
      </div>

      <div className="mt-8 w-full max-w-3xl">
        {/* <div className="bg-white rounded-xl shadow-md p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Select an episode for your video.</h3>
          <div className="flex">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Type your question here..."
              className="flex-1 border border-gray-300 rounded-l-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={isUploading || isProcessing}
            />
            <Button
              type="primary"
              disabled={!inputValue.trim() || isUploading || isProcessing}
              className="rounded-r-lg"
            >
              Send
            </Button>
          </div>
        </div> */}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-5 rounded-xl shadow">
            <h4 className="font-medium text-gray-800 mb-2">Event Query</h4>
            <p className="text-gray-600 text-sm">
              "When did Person X appear in the surveillance footage?"
            </p>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-pink-50 p-5 rounded-xl shadow">
            <h4 className="font-medium text-gray-800 mb-2">Thematic Segmentation</h4>
            <p className="text-gray-600 text-sm">
              Segment educational videos into thematic units and summarize key concepts
            </p>
          </div>
          <div className="bg-gradient-to-br from-green-50 to-teal-50 p-5 rounded-xl shadow">
            <h4 className="font-medium text-gray-800 mb-2">Knowledge Point Location</h4>
            <p className="text-gray-600 text-sm">
              Locate precise video segments corresponding to user-specified knowledge points
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadDashboard;