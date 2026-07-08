package com.it.po.dto;

import com.it.po.uo.User;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import lombok.EqualsAndHashCode;



@EqualsAndHashCode(callSuper = false)
@Data
@AllArgsConstructor
@NoArgsConstructor
public class UserDTO extends User implements Serializable {
    private Long id;
    private String name;
    private String image;
}
