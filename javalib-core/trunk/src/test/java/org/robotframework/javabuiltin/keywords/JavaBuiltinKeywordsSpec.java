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


package org.robotframework.javabuiltin.keywords;

import jdave.Specification;
import jdave.junit4.JDaveRunner;

import org.junit.runner.RunWith;
import org.robotframework.jdave.contract.RobotKeywordContract;
import org.robotframework.jdave.contract.RobotKeywordsContract;

@RunWith(JDaveRunner.class)
public class JavaBuiltinKeywordsSpec extends Specification<JavaBuiltinKeywords> {
    public class Any {
        public JavaBuiltinKeywords create() {
            return new JavaBuiltinKeywords();
        }

        public void isRobotKeywordsAnnotated() {
            specify(context, satisfies(new RobotKeywordsContract()));
        }
        
        public void hasSetSystemPropertyKeyword() {
            specify(context, satisfies(new RobotKeywordContract("setSystemProperty")));
        }
        
        public void setsSystemProperties() {
            context.setSystemProperty("someProperty", "someValue");
            specify(System.getProperty("someProperty"), "someValue");
        }
    }
}
