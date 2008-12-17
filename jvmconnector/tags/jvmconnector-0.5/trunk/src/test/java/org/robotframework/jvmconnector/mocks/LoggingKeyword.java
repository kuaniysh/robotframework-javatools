/*
 * Copyright 2008 Nokia Siemens Networks Oyj
 *  
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.robotframework.jvmconnector.mocks;

import org.robotframework.javalib.keyword.Keyword;


public class LoggingKeyword implements Keyword {
	public static final String LOG_STRING_STDOUT = "mock keyword executing";
	public static final String LOG_STRING_STDERR = "some error occurred";
	public static final Object RETURN_VALUE = Boolean.TRUE;
	public static final String KEYWORD_NAME = "LoggingKeyword";

	public Object execute(Object[] arg0) {
		System.out.print(LOG_STRING_STDOUT);
		System.err.print(LOG_STRING_STDERR);
		return RETURN_VALUE;
	}
	
	public String getName() {
		return KEYWORD_NAME;
	}
}